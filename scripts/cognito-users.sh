#!/usr/bin/env bash
# LAPTOP. Creates one synthetic test resident per council in the Cognito pool
# (idempotent). The council is set HERE, by an administrator, as custom:tenant.
# Passwords are generated, stored as SecureString in SSM Parameter Store
# (/deskville/test-users/<council>) and never printed.
set -euo pipefail
tf="$(cd "$(dirname "$0")/../infra/foundation" && pwd)"
pool="$(terraform -chdir="$tf" output -raw cognito_user_pool_id)"
export AWS_REGION="${AWS_REGION:-eu-west-2}"

for council in wigan bury; do
  user="test-resident-$council"
  param="/deskville/test-users/$council"
  if ! aws cognito-idp admin-get-user --user-pool-id "$pool" --username "$user" >/dev/null 2>&1; then
    aws cognito-idp admin-create-user --user-pool-id "$pool" --username "$user" \
      --user-attributes Name=custom:tenant,Value="$council" Name=name,Value="Test resident ($council)" \
      --message-action SUPPRESS >/dev/null
    echo "created $user"
  else
    echo "exists  $user"
  fi
  if ! aws ssm get-parameter --name "$param" >/dev/null 2>&1; then
    python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("Dv-" + "".join(secrets.choice(a) for _ in range(20)) + "!7a")' \
      | { read -r pw; aws ssm put-parameter --name "$param" --type SecureString --value "$pw" >/dev/null; }
  fi
  aws ssm get-parameter --name "$param" --with-decryption --query Parameter.Value --output text \
    | { read -r pw; aws cognito-idp admin-set-user-password --user-pool-id "$pool" --username "$user" --password "$pw" --permanent; }
  echo "  password set from $param (not printed); council: $(aws cognito-idp admin-get-user --user-pool-id "$pool" --username "$user" \
    --query "UserAttributes[?Name=='custom:tenant'].Value | [0]" --output text)"
done
