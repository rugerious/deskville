#!/usr/bin/env bash
# LAPTOP. Seeds test data (master), then runs the isolation suite as deskville_app
# logged in with an IAM token (no password exists for that role), then shows
# why FORCE matters. Exits non-zero if anything fails. Tunnel must be up.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tests="$here/../db/tests"
cd "$here/../infra/database"
db_host="$(terraform output -raw db_address)"
db_name="$(terraform output -raw db_name)"
app_conn="host=localhost port=15432 dbname=$db_name user=deskville_app sslmode=require"

echo "== 1/4 seed test data (master user; RLS is forced, so the seed sets the tenant too)"
"$here/db-psql.sh" -X -q -f "$tests/seed.sql" >/dev/null && echo "seeded"

echo "== 2/4 deskville_app with a password must be refused (it has none: IAM only)"
if PGPASSWORD="guess-$RANDOM" psql "$app_conn" -X -q -c "select 1" >/dev/null 2>/tmp/deskville-pw.err; then
  echo "FAIL  password login succeeded"; exit 1
else
  echo "PASS  password login refused: $(head -1 /tmp/deskville-pw.err | sed 's/.*FATAL: *//')"
fi

echo "== 3/4 isolation suite as deskville_app (IAM token, valid 15 minutes)"
PGPASSWORD="$(aws rds generate-db-auth-token --hostname "$db_host" --port 5432 --region eu-west-2 --username deskville_app)" \
  psql "$app_conn" -X -q -c "select current_user, session_user" -f "$tests/isolation.sql"

echo "== 4/4 demo: why FORCE (owner without FORCE, inside a rolled-back transaction)"
"$here/db-psql.sh" -X -q -f "$tests/owner_bypass_demo.sql"
