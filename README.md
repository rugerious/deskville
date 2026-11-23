# Deskville

One platform, many towns, and not a single byte allowed to cross between them.

Deskville is a multi-tenant assistant platform on AWS. Each town (tenant) gets its own site and its own assistant that answers residents' everyday questions: bin collections, council tax, parking, licences. All tenants share the same infrastructure, and none of them can ever see another's data.

That last sentence is the whole point. Sharing infrastructure is cheap. Proving that sharing is safe is the hard part, and it's the part this project sets out to measure.

> **Unofficial demonstration.** This project is not affiliated with, endorsed by or operated on behalf of any council. Public information is reused under its licence and attributed to its source. All resident data in this project is fictional.

## Tenants

| Tenant | Content source | Licence |
|---|---|---|
| Bury | bury.gov.uk public pages | Open Government Licence v3.0 (non-commercial re-use), attributed |
| Wigan | wigan.gov.uk open data; page text pending a re-use request | Open Government Licence v3.0 (open data) |

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
| 2 | Database: PostgreSQL + pgvector, row-level security | 🚧 stack and lab switch | |
| 3 | Content: licensed public pages, synthetic records, canaries | ⏳ | |
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

## How changes reach AWS

No long-lived AWS keys exist anywhere. GitHub Actions proves who it is with a short-lived OIDC token, and AWS hands back a role for one hour.

| When | Role | Can do |
|---|---|---|
| Pull request | `deskville-github-plan` | Read-only, plus the state lock file. Cannot read any S3 object outside the state bucket, nor secret values. |
| Merge to `main`, after manual approval in the `production` environment | `deskville-github-apply` | Build infrastructure. In IAM it can only create `deskville-*` roles, and only if they carry the `deskville-boundary` permissions boundary. It can never modify its own role, the plan role, or the boundary. |

Every apply is followed by a second plan that must report no changes.

### Switching the lab on and off

Some parts cost money by the hour (the database, later the load balancer and containers). Those are never created by a merge: a pull request still shows their plan, but they are switched on and off only by the manual `lab` workflow (`up` or `down`), which also waits for approval. Nothing expensive can be left running by accident through the normal pipeline.

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
db/
  migrations/   schema, roles and row-level security (applied in order, once)
  tests/        isolation suite (runs as the application role, with an IAM token)
scripts/        db-tunnel.sh (port-forward through the bastion), db-psql.sh,
                db-migrate.sh, db-isolation-test.sh
docs/           decisions
```

## Cost discipline

Everything is Terraform. The expensive parts are created when needed and destroyed afterwards. A monthly budget alarm guards the account.

## Acknowledgements

Built with Claude (Anthropic) as a pair programmer. Every change was reviewed, tested and merged by me.
