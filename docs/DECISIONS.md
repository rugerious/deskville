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

## D14. PostgreSQL 18.6 on db.t4g.micro, gp3
On RDS since 26 August 2026 (past the 14-day rule); the release notes of 18.4 updated pgvector to 0.8.2. The cheapest Graviton class that runs it. Single-AZ: this is a lab, and Multi-AZ would double the cost for an availability we don't need to prove yet. The account has no Free Tier credits, so every hour is paid: hence D17.

## D15. RDS keeps the master password
`manage_master_user_password` creates the password in Secrets Manager and rotates it. Terraform only ever knows the secret's ARN, so the password never reaches the state, and the plan role's deny on secret values (D13) never gets in the way.

## D16. An SSM-only bastion is the only way in
The database lives in subnets with no route to the internet and accepts PostgreSQL only from the bastion's security group. The bastion has no inbound rules at all: access is a Session Manager port-forward, authenticated by IAM, logged by AWS. It needs a public IP only so its SSM agent can reach AWS (there is no NAT). Later, the containers get the same kind of rule as the bastion.

## D17. Expensive stacks are switched on deliberately, never by a merge
The database stack is planned on every pull request, but only the manual `lab` workflow creates or destroys it, and that workflow waits for approval in `production`. If the database followed the normal merge-to-apply path, any change to its code would switch it back on and start the meter. After `down`, the workflow checks that the stack's state is empty.

## D18. Lab settings, stated honestly
No final snapshot, no deletion protection, one day of backups, minor upgrades pinned. Right for a lab that is rebuilt from code on every `up`; wrong for production, where it would be the opposite on every line.

## D19. The application has no database password
`deskville_app` is a member of `rds_iam`, so it can only log in with a 15-minute token signed by an IAM identity; a password login is refused because no password exists. Together with OIDC in CI and SSM at the bastion, there is no long-lived credential anywhere between GitHub and the data. Cost: every new connection needs a token (a local signing operation, no network call) and IAM authentication adds a little latency per connection; at large scale a pool or RDS Proxy would absorb that.

## D20. Row-level security, forced, failing closed
Every tenant table carries `tenant_id`; RLS is enabled and forced, so even the table owner obeys it. Policies compare against `app.current_tenant()`, which reads the transaction setting `app.tenant_id` and raises an error when it is missing: a forgotten tenant must look like a bug, never like an empty result. The application role owns nothing, cannot bypass RLS, cannot alter tables and cannot become the owner.
**Honest limit:** the application sets `app.tenant_id` from the verified token. RLS protects against query bugs (a missing `WHERE`, a wrong join, a similarity search across tenants); it does not protect against a compromised application process, which could set any tenant. That threat is answered at the edge (layer 5: the tenant comes only from the signed token).

## D21. Migrations are plain SQL, applied once, in order
`scripts/db-migrate.sh` applies `db/migrations/*.sql` each in its own transaction and records it in `public.deskville_migrations`; a second run skips everything. No framework: the files are readable on their own, and the schema is rebuilt from them on every `lab up`.

## D22. The isolation suite proves the dangerous paths, as the application
It runs as `deskville_app` with an IAM token, never as an administrator. Seeded data includes canary strings, and Bury's test vector is deliberately closer to the query than Wigan's: a similarity search that ignored the tenant would return Bury first. Twelve checks: no tenant → error; each tenant reads only its own rows, requests and tenant record; vector search stays inside the tenant; no inserting, updating, deleting or moving rows across tenants; no disabling RLS; no becoming the owner. A rolled-back demonstration shows what the owner would see without `FORCE`.
Before its first run on RDS, the suite was run against a local PostgreSQL 16 (with `real[]` standing in for `vector`): 12/12 PASS; with RLS disabled on `documents` as a mutation test, 8 checks FAILED and the script exited non-zero. A test that has never been seen failing has not been tested.

## D23. On RDS, the master user bypasses row-level security
Found on the first run against RDS (23 Nov): the master user has neither `rolsuper` nor `rolbypassrls`, yet it read the tenant tables with no tenant set, while `deskville_owner` on the same tables, with FORCE, got "app.tenant_id is not set". The only difference between the two sessions is membership of `rds_superuser`. Consequences: the application never uses the master user (it never could: it has no access to its secret); the seed runs as `deskville_owner`, so it is held by the policies like everyone else; every delete in test data is scoped by `tenant_id`, never by title alone. The master user is treated for what it is: an administrator who sees everything, whose password lives only in Secrets Manager.

## D24. A check that evaluates to NULL is a failure
The first RDS run also exposed a bug in the suite itself: a comparison with "no result" is NULL in SQL, and `WHERE NOT ok` does not count NULL. One failing check was shown as FAIL but not counted. Now `ok` is `NOT NULL`, every condition is wrapped in `coalesce(..., false)`, the final count uses `ok IS NOT TRUE`, and a check that finds nothing to test reports that it proves nothing. Re-tested locally by deleting Wigan's document: 3 FAIL, all 3 counted, non-zero exit.

## D25. Service requests are synthetic, reproducible and built to catch mix-ups
Each council gets 200 made-up service requests from `scripts/gen-service-requests.py`, with a fixed seed: running it twice gives byte-identical CSVs, so the data in the repo can always be regenerated and checked. There are no names, emails, phone numbers or street addresses; the area is a public town name. Categories exist only where a content doc exists, and each request points to its doc (`doc_id`). Status follows age (last week's requests are mostly open, older ones mostly resolved), references follow creation order, and updates fall in office hours, so the data behaves like a real case system rather than random noise. The two councils use different reference formats (`WGN-26-006985`, `BRY/2026/07376`) and their own bin colours: an assistant that mixes tenants gives itself away.

## D26. Loading under RLS: COPY is refused, and RLS cannot catch the wrong file
Found in the local test before the first run: PostgreSQL refuses `COPY FROM` into a table with row-level security. The loader copies the CSV into a temporary table (no RLS, dropped at commit) and then uses `INSERT ... SELECT`, which the policy checks row by row as `deskville_owner` with the tenant set. Second finding: RLS guarantees a row lands in the tenant that is set, but it cannot know the file was the wrong one; Bury's file loaded under Wigan would have been accepted as Wigan data. The loader therefore checks every reference against the tenant's format and rolls back on a mismatch. Tested locally: load, reload (same counts, `TEST-*` rows untouched), and Bury's file in Wigan's place → error, exit 3, Wigan's data unchanged.

## D27. Tenants are configuration, not test fixtures
Found in the first lab session with real data (24 Nov): the two tenant rows were created only by the isolation suite's seed, so on a fresh database the request loader would have failed on the foreign key unless the tests happened to run first. Real data must not depend on test data. Migration `004_tenants.sql` now creates both tenants (as `deskville_owner`, each with its own tenant set, idempotent); the seed's own insert stays as `ON CONFLICT DO NOTHING`. Tested locally on emptied tables: applied twice, one tenant row visible to each tenant.

## D28. Content lives in Git and is copied to one S3 bucket, a prefix per council, with ABAC
Options compared on criteria first (source of truth, testable isolation, survives the lab cycle, matches the real product, effort, reversibility): read straight from the repo (A), one bucket with a prefix per council (B), one bucket per council (C). Chosen: B. Git stays the source of truth (every change reviewed in a PR); after an approved merge, CI copies `content/<tenant>/*.md` to `<tenant>/docs/` in the content bucket. Embeddings already computed are cached under `<tenant>/cache/`, because a vector is tenant data too. The ingestion role `deskville-ingest` can only be assumed with a session tag `tenant` set to a known council, and its single policy reaches only `${aws:PrincipalTag/tenant}/...`: a Wigan session cannot read, list or write anything under `bury/`. That is a second, independent isolation layer before the database's row-level security. C (a bucket per council) is the stronger "silo" option and stays available for a client who demands it; it grows with every council. Honest limit: today the tag is chosen by whoever assumes the role (the laptop); in layer 5 it must come from the platform (the signed token), never from the caller. The bucket name has a random suffix instead of the account ID, and CI masks the account ID, because the logs of a public repository are public.

## D29. Bedrock models: Titan Text Embeddings V2 and Nova Lite, in London, rate-limited
Bedrock was blocked on this account until 25 Nov: every on-demand model in eu-west-2 had an applied quota of 0, not adjustable, and every call returned `ThrottlingException`, which names the symptom, not the cause. An AWS Support case (open since 22 Oct) applied Titan Text Embeddings V2 in London at 60 requests and 300,000 tokens per minute; Amazon Nova Lite and Micro have 100 requests and 4,000,000 tokens per minute; Anthropic models stay restricted for this account's history. Both models were called successfully in eu-west-2 with their plain model IDs, so no data leaves the UK (D3 holds). Consequences: ingestion embeds one chunk per request at no more than one request per second, retries with backoff, and skips unchanged chunks through the cache; the embedder and the generator are swappable by configuration, so one model refusal never stops the project.

## D30. Chunking by section, embeddings cached in S3 before the database exists
Each `## ` section of a document is one resident question with its answer, so a chunk is one section (sections over 1,500 characters would be split at paragraph boundaries; none is today). Each chunk's text starts with the council and the document title ("Bury - Bin collection days…: Which bin is which?"), so the same question in two councils never produces the same text, and the bin-colour trap survives into the vectors. Front matter is metadata, never embedded: sources and the date read travel with every chunk, because answers must link the source and say how old the information is (one of Wigan's conditions for re-use). Text before the first section is never dropped (the canaries' banner becomes its own chunk). Result on 25 Nov: 189 chunks (Wigan 96, Bury 93), about 10,000 tokens, median 220 characters. Embeddings are computed per council inside its own ABAC session (it reads its documents from its own S3 prefix and writes to its own cache), at no more than one Titan request per second with backoff on throttling, and cached under `<council>/cache/titan-v2/<sha256(model|dimensions|text)>.json`: unchanged text is never embedded twice, and a model change changes every key. The cache makes the lab-day load independent of Bedrock. Documents marked `visibility: internal` (the canaries) are embedded like the rest so the cross-council test is real, but resident search will only ever return `public` chunks: isolation by audience inside one council, tested separately. Standard library plus the AWS CLI: no new dependencies.

## D31. Vector search goes through one function, and the HNSW trap is tested, not assumed
Migration 005 turns `app.documents` into chunks with their metadata (document, section, sources, date read, visibility, cache key), one row per chunk per council, and adds an HNSW index (cosine). Residents' searches go through `app.search_public(query, k)`: public chunks only, `SECURITY INVOKER` so row-level security applies to the caller, and `hnsw.iterative_scan = relaxed_order` set on the function itself. The trap it guards against: an HNSW scan picks the nearest vectors first and RLS filters them afterwards, so without iterative scans a council can get fewer results than it asked for. Found locally on 25 Nov with real pgvector 0.8.2: on a table this small the planner prefers the tenant index and an exact sort (safe), so the test forces the vector index the way a large table would get it, checks the plan really uses it, and compares: iterative scan off, 5 of 10 results; on, 10 of 10. The loader writes as the owner with the tenant set and refuses another council's content (same guard as D26); it never calls Bedrock (the S3 cache, D30). The search suite runs as the application role and counts isolation, canary, audience and HNSW checks as the gate; top-1 relevance is reported as a quality number, not a gate. Mutation test: with RLS switched off, isolation 0/12, canary 0/2, exit 3. Honest limit: staff and resident searches share one database role today; separate roles per audience belong to layer 5.

## D32. Every workflow masks the account ID, and old logs that show it are deleted
Checked on 25 Nov after adding the mask to `terraform.yml` (#20): the `lab` workflow had no mask, and its public logs printed the account ID (4 lines in a `lab up` run, 20 in a `lab down` run: the database stack's ARNs). An AWS account ID is not a credential, but this project's rule is that it never appears in public, because it narrows reconnaissance (which account to target, which role names to guess). Every workflow now masks it right after assuming a role (`::add-mask::`), and the logs of earlier runs that contain it are deleted. The check is the same one used for commits: grep the log for the values in the local forbidden-patterns file, expect 0.

## D33. One domain, a subdomain per council, and the host name never picks the data
`deskville.co.uk` (registered outside AWS) is delegated to a Route 53 hosted zone created by hand, like the state bucket; Terraform only reads it. Each council gets a subdomain (`wigan.`, `bury.`), the API gets `api.`, and one wildcard ACM certificate covers them all: a third council costs one more subdomain. The host name is part of the request, so it may choose which site is shown, never which council's data is read: that comes from the token (D34). A council's site with another council's token is refused (403). The domain is one Terraform variable, so changing it later is one line. Names avoid anything that could pass for official (no "council", no "gov").

## D34. The API verifies the token itself; the council comes from the token and nothing else
Every request's `Authorization: Bearer` token is verified by the API, not only by something in front of it: RS256 signature against the Cognito pool's public keys (JWKS, cached), issuer, audience (the app client), `token_use`, expiry. Only then is `custom:tenant` read and set, LOCAL to that request's transaction, so a pooled connection never carries a council into the next request. Query parameters, headers (`X-Tenant`, `X-Forwarded-Host`) and the host name cannot change it. Why not leave it to the load balancer: a header written by the ALB can be forged by anything that reaches the container another way; verifying the signature where the data is read holds however the request arrived, and it can be tested without AWS. A check at the edge can still be added on top, never instead. Cognito ID tokens are used, not access tokens: Cognito only puts custom attributes in access tokens through a pre-token-generation Lambda on a paid tier; the ID token's `aud` is checked against the app client. Every refusal is the same short answer to the caller ("invalid token"); the reason is logged. A library does the cryptography (PyJWT, pinned); the tests forge tokens every known way (another key, `alg: none`, HS256 with the public key, changed payload, expired, wrong issuer or audience, access token, unknown key id) and all are refused. Mutation tests: with signature checks off, 7 of those tests fail; reading the council from `?tenant=`, the "query parameter ignored" test fails.

## D35. One Cognito user pool with a custom:tenant attribute only an admin can write
Same model as the database (pooled, RLS) and storage (pooled, ABAC): one user pool, each user carries `custom:tenant`, which the app client can read but never write, so a resident cannot move themselves to another council. One pool means one set of password, MFA and token policies to get right, and a new council is one more attribute value. The honest cost: isolation rests on one attribute set by an admin, and a council cannot have its own sign-in rules. A pool per council ("silo") stays the premium option for a client who requires it by contract or regulation; the API is unchanged by it (issuer and audience per council).

## D36. One API image, built natively for ARM, immutable, scanned before it can be used
The API ships as one container image: the official Python 3.13 slim base (from ECR Public's mirror, which avoids Docker Hub's anonymous pull limits), dependencies pinned (D16), the Amazon RDS certificate bundle so the database's certificate is verified (`sslmode=verify-full`), and a non-root user. It is built on GitHub's ARM runners (native arm64 for Graviton Fargate, no emulation), only after the API tests pass and after approval in the `production` environment, and pushed to ECR tagged with the commit. Tags are immutable, so a tag always means the same image and a deployment can name exactly what it runs. Every push is scanned (ECR basic scanning, free); a CRITICAL finding fails the job. Old images expire (untagged after a day, beyond the 10 newest). The registry is always on and costs cents; the containers that run the image follow the lab cycle (5.4). Dependabot now watches the API's Python packages and its base image; updates still wait for the 14-day rule.
