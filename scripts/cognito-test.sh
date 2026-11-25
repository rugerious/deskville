#!/usr/bin/env bash
# LAPTOP. Layer 5.3 proof against the real Cognito pool:
#  1. each test resident signs in and gets an ID token naming their council;
#  2. the API's own TokenVerifier (D34) accepts it, using Cognito's real public keys;
#  3. a resident cannot change their own council (the app client may not write it);
#  4. a token signed by anyone else is refused by the same verifier.
# Exit code = number of failures.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tf="$root/infra/foundation"
pool="$(terraform -chdir="$tf" output -raw cognito_user_pool_id)"
client="$(terraform -chdir="$tf" output -raw cognito_app_client_id)"
export AWS_REGION="${AWS_REGION:-eu-west-2}"
venv="$root/api/.venv"
[ -x "$venv/bin/python" ] || { python3 -m venv "$venv" && "$venv/bin/pip" install -q -r "$root/api/requirements.txt"; }
fails=0
pass() { printf "PASS  %-58s %s\n" "$1" "$2"; }
fail() { printf "FAIL  %-58s %s\n" "$1" "$2"; fails=$((fails+1)); }

for council in wigan bury; do
  user="test-resident-$council"
  auth=$(aws ssm get-parameter --name "/deskville/test-users/$council" --with-decryption --query Parameter.Value --output text \
    | { read -r pw; aws cognito-idp initiate-auth --client-id "$client" --auth-flow USER_PASSWORD_AUTH \
          --auth-parameters "USERNAME=$user,PASSWORD=$pw" --query 'AuthenticationResult.[IdToken,AccessToken]' --output text; })
  id_token=$(echo "$auth" | cut -f1); access_token=$(echo "$auth" | cut -f2)
  [ -n "$id_token" ] && [ "$id_token" != "None" ] || { fail "$council: sign in" "no token"; continue; }

  # 2. The API's verifier, Cognito's real JWKS.
  out=$(cd "$root/api" && ID_TOKEN="$id_token" POOL="$pool" CLIENT="$client" "$venv/bin/python" - <<'PY'
import os, jwt
from app.auth import TokenVerifier, AuthError
from app.config import Settings
s = Settings(user_pool_id=os.environ["POOL"], app_client_id=os.environ["CLIENT"])
v = TokenVerifier(s.issuer, s.app_client_id, s.tenants, jwt.PyJWKClient(s.jwks_url))
try:
    print("council=" + v.verify("Bearer " + os.environ["ID_TOKEN"]))
except AuthError as e:
    print(f"refused {e.status}: {e.reason}")
PY
)
  [ "$out" = "council=$council" ] && pass "$council: signs in; the API's verifier reads its council" "$out" \
                                  || fail "$council: signs in; the API's verifier reads its council" "$out"

  # 3. The resident tries to move themselves to the other council.
  other=bury; [ "$council" = bury ] && other=wigan
  err=$(aws cognito-idp update-user-attributes --access-token "$access_token" \
          --user-attributes Name=custom:tenant,Value="$other" 2>&1 >/dev/null)
  now=$(aws cognito-idp admin-get-user --user-pool-id "$pool" --username "$user" \
          --query "UserAttributes[?Name=='custom:tenant'].Value | [0]" --output text)
  if echo "$err" | grep -q NotAuthorizedException && [ "$now" = "$council" ]; then
    pass "$council: cannot change own council to $other" "refused; still $now"
  else
    fail "$council: cannot change own council to $other" "err='$(echo "$err" | tail -1)' now=$now"
  fi
done

# 4. A token signed by someone else, claiming Bury, with the same issuer and audience.
out=$(cd "$root/api" && POOL="$pool" CLIENT="$client" "$venv/bin/python" - <<'PY'
import os, time, jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from app.auth import TokenVerifier, AuthError
from app.config import Settings
s = Settings(user_pool_id=os.environ["POOL"], app_client_id=os.environ["CLIENT"])
real_kid = jwt.PyJWKClient(s.jwks_url).get_signing_keys()[0].key_id
mine = rsa.generate_private_key(public_exponent=65537, key_size=2048)
now = int(time.time())
forged = jwt.encode({"iss": s.issuer, "aud": s.app_client_id, "token_use": "id", "iat": now, "exp": now + 600,
                     "custom:tenant": "bury"}, mine, algorithm="RS256", headers={"kid": real_kid})
v = TokenVerifier(s.issuer, s.app_client_id, s.tenants, jwt.PyJWKClient(s.jwks_url))
try:
    print("ACCEPTED council=" + v.verify("Bearer " + forged))
except AuthError as e:
    print(f"refused {e.status}: {e.reason}")
PY
)
echo "$out" | grep -q "^refused 401" && pass "forged token (Cognito's key id, my own key) refused" "$out" \
                                      || fail "forged token (Cognito's key id, my own key) refused" "$out"
echo
[ $fails -eq 0 ] && echo "all Cognito checks passed" || echo "$fails check(s) FAILED"
exit $fails
