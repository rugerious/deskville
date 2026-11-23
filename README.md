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

## Repository layout

```
infra/
  bootstrap/    S3 bucket for Terraform state (run once, local state)
  foundation/   VPC, subnets, gateway endpoints, budget alarm
docs/           decisions and build log
```

## Cost discipline

Everything is Terraform. The expensive parts are created when needed and destroyed afterwards. A monthly budget alarm guards the account.

## Status

Foundations in progress.
