# Decisions

Each decision records what was chosen, what was rejected, and why. These are the answers to "why did you do it this way?"

## D1. Region: eu-west-2 (London)
The tenants are UK councils, so data stays in the UK.

## D2. Terraform state in S3 with native locking
S3 versioning keeps every previous state. `use_lockfile = true` (Terraform 1.10+) gives locking without a DynamoDB table. The bucket denies non-HTTPS requests and blocks all public access.

## D3. No NAT Gateway
A NAT Gateway charges by the hour whether used or not. The database lives in private subnets with no internet route at all, which is both cheaper and stricter. Containers will run in public subnets but accept traffic only from the load balancer's security group.
**With a company budget:** containers in private subnets behind NAT or interface endpoints, so no task ever has a public IP.

## D4. Free gateway endpoints for S3 and DynamoDB
They cost nothing and keep that traffic on the AWS network.

## D5. Default security group locked
Taken over by Terraform with no rules, so nothing can use it by accident.

## D6. Budget alarm before anything that costs money
USD 10 per month, alerts at 50% and 100% actual, and 100% forecast. It counts only costs tagged `Project=deskville`; the account-wide safety net is a separate budget. Alerts go to a verified address only: since 30 September 2026 AWS requires budget recipients to verify, and an unverified address receives nothing, with no warning.

## D7. Same cost tags as every project in the account
`Project`, `Environment` and `ManagedBy` are the activated cost allocation tags, so every resource carries all three (`Stack` is extra, for reading the console).

## D8. Pinned versions, at least 14 days old
Terraform 1.16.6 (`.terraform-version`) and AWS provider 6.72.0. A version that has been out for two weeks has had time to show its bugs. Upgrades are deliberate PRs.

## D9. Pre-commit guard for private values
The hook blocks any added line containing a value from a file outside the repo (`~/.config/deskville/forbidden-patterns`): the account ID (also in its dashed form) and private email addresses. The repo knows the rule, never the values. GitHub secret scanning covers secret formats; this covers our own identifiers.

## D10. CI with OIDC, two roles, no stored keys
Pull requests assume a read-only plan role; merges assume an apply role only from the `production` environment, which needs manual approval. Both trust policies accept the name form and the immutable-ID form of the token's `sub` claim (`repo:owner@id/name@id:...`), because GitHub may send either. The account's single GitHub OIDC provider belongs to another project and is read with a `data` source, never created twice.

## D11. CI cannot change its own trust
The roles and the boundary live in `infra/ci/`, applied from a laptop. The apply role is explicitly denied any change to `deskville-github-*` roles and to the boundary policy.

## D12. Permissions boundary from day one
Every role CI creates must carry `deskville-boundary` (enforced by a condition on `iam:CreateRole`), and removing a boundary is denied. The boundary allows workload services but denies IAM, Organizations and account changes, and any access to the Terraform state. So even a role created with a mistaken policy can never escalate. Cost: whenever a future role legitimately needs something the boundary denies, the boundary changes first, by hand, in `infra/ci/`.

## D13. The plan role reads only the state bucket
`ReadOnlyAccess` alone could read every S3 object in the account, including other projects' data. An explicit deny limits `s3:GetObject` to the state bucket, and secret values (`secretsmanager:GetSecretValue`, `kms:Decrypt`) are denied too. Expected side effect: when Terraform starts managing S3 objects or secrets, the plan will be refused and this deny will need a precise exception (lesson from the previous project, where exactly that happened).
