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
USD 10 per month, alerts at 50% and 100% actual, and 100% forecast.
