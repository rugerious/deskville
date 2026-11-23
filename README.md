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

| # | Layer | Status |
|---|---|---|
| 0 | Foundations: state bucket, VPC, budget | ✅ 23 Nov 2026 |
| 1 | Database: PostgreSQL + pgvector, row-level security | ⏳ |
| 2 | Content: licensed public pages, synthetic records, canaries | ⏳ |
| 3 | Ingestion: chunking and embeddings, tenant stamped | ⏳ |
| 4 | API and containers: ECS Fargate, ALB, Cognito | ⏳ |
| 5 | Assistant: retrieval, tools, Guardrails | ⏳ |
| 6 | Sites: CloudFront and WAF | ⏳ |
| 7 | Proof: isolation suite, answer-quality evaluation, cost per tenant | ⏳ |
| 8 | Observability: OpenTelemetry tracing | ⏳ |
| 9 | CI/CD: GitHub Actions with OIDC | ⏳ |

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

## Repository layout

```
.githooks/      pre-commit guard (values it blocks live outside the repo)
infra/
  bootstrap/    S3 bucket for Terraform state (run once, local state)
  foundation/   VPC, subnets, gateway endpoints, budget
docs/           decisions
```

## Cost discipline

Everything is Terraform. The expensive parts are created when needed and destroyed afterwards. A monthly budget alarm guards the account.

## Acknowledgements

Built with Claude (Anthropic) as a pair programmer. Every change was reviewed, tested and merged by me.
