# Deskville

One platform, many towns, and not a single byte allowed to cross between them.

Deskville is a multi-tenant assistant platform on AWS. Each town (tenant) gets its own site and its own assistant that answers residents' everyday questions: bin collections, council tax, parking, licences. All tenants share the same infrastructure, and none of them can ever see another's data.

That last sentence is the whole point. Sharing infrastructure is cheap. Proving that sharing is safe is the hard part, and it's the part this project sets out to measure.

> **Unofficial demonstration.** This project is not affiliated with, endorsed by or operated on behalf of any council. Council content is written in our own words from facts on the councils' public pages, and every document links its sources. All resident data in this project is fictional.

## Tenants

| Tenant | Content | Resident data |
|---|---|---|
| Wigan | 20 documents written in our own words from facts on wigan.gov.uk, each linking its sources | 200 synthetic service requests |
| Bury | 20 documents written in our own words from facts on bury.gov.uk, each linking its sources | 200 synthetic service requests |

Same topics for both councils, on purpose: similar questions produce similar embeddings, which makes the isolation tests demanding. Details in [`content/README.md`](content/README.md).

## Architecture (target)

- **Edge:** CloudFront and WAF in front of one static site per tenant, same code.
- **Identity:** Cognito. The tenant comes from the signed token, never from the request.
- **Network:** a VPC across two availability zones. Public subnets for the load balancer and containers, private subnets with no internet route for the database. No NAT Gateway, by design.
- **Compute:** ECS Fargate (ARM, Spot) behind an Application Load Balancer.
- **Data:** PostgreSQL with pgvector. Structured data and document embeddings live side by side, and row-level security enforces tenant isolation inside the database itself.
- **AI:** Amazon Bedrock for embeddings, generation and Guardrails.
- **Proof:** an isolation test suite (canary data that must never leak across tenants) and an answer-quality evaluation.

## Progress

Layers are numbered in the order they are built.

| # | Layer | Status | Evidence |
|---|---|---|---|
| 0 | Foundations: state bucket, VPC, budget | ✅ 23 Nov 2026 | [#1](https://github.com/rugerious/deskville/pull/1): private subnets have no route to the internet ([proof below](#what-is-built-so-far)) |
| 1 | CI/CD: GitHub Actions with OIDC, approved applies | ✅ 23 Nov 2026 | [#2](https://github.com/rugerious/deskville/pull/2): first run approved, apply 0 added / 0 changed / 0 destroyed, drift check clean |
| 2 | Database: PostgreSQL + pgvector, forced row-level security, IAM-only app role | ✅ 23 Nov 2026 | Isolation suite 12/12 on RDS, run as the application ([output below](#isolation-proven-on-the-real-database)) |
| 3 | Content: council documents, synthetic service requests, canaries | ✅ 24 Nov 2026 | [#13](https://github.com/rugerious/deskville/pull/13) [#14](https://github.com/rugerious/deskville/pull/14) [#15](https://github.com/rugerious/deskville/pull/15) [#16](https://github.com/rugerious/deskville/pull/16) [#17](https://github.com/rugerious/deskville/pull/17) [#18](https://github.com/rugerious/deskville/pull/18): 40 documents, 400 requests loaded on RDS; as the application, a real Bury reference returns nothing to Wigan ([output below](#content-and-resident-data)) |
| 4 | Ingestion: chunking and embeddings, tenant stamped | ⏳ | |
| 5 | API and containers: ECS Fargate, ALB, Cognito | ⏳ | |
| 6 | Assistant: retrieval, tools, Guardrails | ⏳ | |
| 7 | Sites: CloudFront and WAF | ⏳ | |
| 8 | Case study: the numbers (isolation, accuracy, cost per tenant) | ⏳ | |

Isolation tests and tracing are not a layer at the end: they start at layer 2 and grow with every layer after it.

## What is built so far

**Layer 0: foundations.** A VPC across two availability zones (eu-west-2a, eu-west-2b) with public subnets for what must face the internet and private subnets for the database. Terraform state lives in a versioned, encrypted, HTTPS-only S3 bucket with native locking.

The private subnets have no route to the internet, in either direction. That is a design claim, so it gets checked against the real API rather than the code:

```
$ aws ec2 describe-route-tables --route-table-ids <private-rt> \
    --query "RouteTables[0].Routes[].[DestinationCidrBlock,DestinationPrefixListId,GatewayId]"
|  10.20.0.0/16 |  None        |  local          |
|  None         |  pl-7ca54015 |  vpce-0d70...   |   <- S3 gateway endpoint
|  None         |  pl-b3a742da |  vpce-00f8...   |   <- DynamoDB gateway endpoint
```

Three routes: traffic inside the VPC, and two free gateway endpoints that keep S3 and DynamoDB traffic on the AWS network. No `0.0.0.0/0`. A database placed here can neither be reached from the internet nor reach out to it.

Guardrails in place before anything costs money: a monthly budget on everything tagged `Project=deskville`, Terraform and provider versions pinned, and a pre-commit hook that refuses any commit containing the account ID or private addresses.

**Layer 2: the database.** PostgreSQL 18.6 on RDS (Graviton), pgvector 0.8.2, in subnets with no route to the internet, reachable only through an SSM bastion with no inbound rules. TLS is forced: a connection without encryption is refused before any password is checked. The application role has no password at all; it logs in with a 15-minute IAM token.

### Isolation, proven on the real database

Every table carries a `tenant_id`; row-level security is enabled and forced, and a session without a tenant gets an error, not an empty result. The suite below runs as the application role, logged in with an IAM token, against seeded data that includes canary strings, and a Bury vector placed deliberately closer to the query than Wigan's, so a similarity search that ignored the tenant would return Bury first.

```
 current_user = deskville_app (IAM token; a password login is refused: "PAM authentication failed")

  1 | PASS | no tenant set -> error, not data           | app.tenant_id is not set
  2 | PASS | Wigan reads only Wigan documents           | own=1 other=0 bury_canary=0
  3 | PASS | Wigan cannot see Bury requests             | bury_requests=0
  4 | PASS | Wigan cannot see the Bury tenant row       | bury_tenant_rows=0
  5 | PASS | vector search as Wigan returns only Wigan  | top result: TEST Wigan bins
  6 | PASS | Wigan cannot insert a row for Bury         | new row violates row-level security policy
  7 | PASS | Wigan cannot update Bury rows              | rows updated=0
  8 | PASS | Wigan cannot delete Bury rows              | rows deleted=0
  9 | PASS | Wigan cannot move its row to Bury          | new row violates row-level security policy
 10 | PASS | app cannot disable RLS                     | must be owner of table documents
 11 | PASS | app cannot become the owner                | permission denied to set role "deskville_owner"
 12 | PASS | Bury reads only Bury (incl. vector search) | wigan_canary=0 top=TEST Bury bins
 NOTICE:  all 12 isolation tests passed
```

Who can see across tenants, and why (from the same run, inside rolled-back transactions):

| Who | FORCE | Tenant set | Sees |
|---|---|---|---|
| Master user (member of `rds_superuser`) | on | no | everything: on RDS it bypasses RLS, so the application never uses it |
| Table owner | off | no | everything: why FORCE is on |
| Table owner | **on** | no | `ERROR: app.tenant_id is not set` |
| Application role | on | no | `ERROR: app.tenant_id is not set` |

The suite has also been seen failing: with RLS switched off on one table it reports 8 failures and exits non-zero, and a missing test row is reported as "proves nothing", never as a pass.

### Content and resident data

- **40 documents** (20 per council) answering the same everyday questions for both: bins, council tax, parking, potholes, licences, planning, Blue Badge, school admissions, births and deaths, contact. Written in our own words from facts on the councils' public pages; each has its sources and the date they were read ([inventory](content/inventory.csv)). The same bin colours mean different things in each council: a leak would give a confident, wrong answer.
- **400 synthetic service requests** from a fixed-seed generator: the same command always produces byte-identical files. No names, emails, phone numbers or addresses; towns only. Each council has its own reference format (`WGN-26-006985`, `BRY/2026/07376`), and each request points to the document that explains its service.
- **Two canary documents**: one fictional internal note per council, on the most-asked topic, with a unique code that must never appear in the other council's results.

Loaded on RDS on 24 Nov (migration 003, then the loader), and read back **as the application role, with an IAM token**, looking up a real Bury reference from each side:

```
   who    | requests | bury_refs | lookup_bury_ref
----------+----------+-----------+-----------------
 as Wigan |      200 |         0 |               0

   who   | requests | wigan_refs |                       own_lookup
---------+----------+------------+---------------------------------------------------------
 as Bury |      200 |          0 | BRY/2026/07376 | in-progress | Prestwich | bury-pothole
```

The same session re-ran the isolation suite: 12/12 PASS. Two things found on the way, before any money was spent ([D26](docs/DECISIONS.md)): PostgreSQL refuses `COPY` into a table with row-level security, so the loader goes through a temporary table and `INSERT ... SELECT`, checked row by row; and RLS guarantees *where* a row lands, not that it was the right file, so the loader also checks every reference against its council's format and rolls back on a mismatch.

## How changes reach AWS

No long-lived AWS keys exist anywhere. GitHub Actions proves who it is with a short-lived OIDC token, and AWS hands back a role for one hour.

| When | Role | Can do |
|---|---|---|
| Pull request | `deskville-github-plan` | Read-only, plus the state lock file. Cannot read any S3 object outside the state bucket, nor secret values. |
| Merge to `main`, after manual approval in the `production` environment | `deskville-github-apply` | Build infrastructure. In IAM it can only create `deskville-*` roles, and only if they carry the `deskville-boundary` permissions boundary. It can never modify its own role, the plan role, or the boundary. |

Every apply is followed by a second plan that must report no changes.

### Switching the lab on and off

Some parts cost money by the hour (the database, later the load balancer and containers). Those are never created by a merge: a pull request still shows their plan, but they are switched on and off only by the manual `lab` workflow (`up` or `down`), which also waits for approval. Nothing expensive can be left running by accident through the normal pipeline.

A lab session, from the laptop: `lab up` → `db-tunnel.sh` → `db-migrate.sh` (the schema is rebuilt from code every time) → `db-seed-requests.sh` → `db-isolation-test.sh` → `lab down`. The session on 24 Nov took about 25 minutes from `up` to `down`.

The two CI roles and the boundary live in `infra/ci/`, which is applied from a laptop and never by CI: a pipeline should not be able to widen its own trust.

## Repository layout

```
.githooks/      pre-commit guard (values it blocks live outside the repo)
.github/        workflows: terraform (plan on PR, approved apply on merge), lab (up/down); Dependabot
infra/
  bootstrap/    S3 bucket for Terraform state (run once, local state)
  ci/           OIDC roles for GitHub Actions + permissions boundary (laptop only)
  foundation/   VPC, subnets, gateway endpoints, budget
  database/     PostgreSQL on RDS + SSM-only bastion (switched by the lab workflow)
content/        council documents (own words, sources linked), inventory, canaries
db/
  migrations/   schema, roles, row-level security, tenants (applied in order, once)
  seed/         synthetic service requests (generated, reproducible)
  tests/        isolation suite (runs as the application role, with an IAM token)
scripts/        db-tunnel.sh (port-forward through the bastion), db-psql.sh,
                db-migrate.sh, db-seed-requests.sh, db-isolation-test.sh,
                gen-service-requests.py
docs/           decisions
```

## Cost discipline

Everything is Terraform. The expensive parts are created when needed and destroyed afterwards. A monthly budget alarm guards the account.

## Acknowledgements

Built with Claude (Anthropic) as a pair programmer. Every change was reviewed, tested and merged by me.
