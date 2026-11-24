#!/usr/bin/env bash
# LAPTOP. Loads the synthetic service requests (db/seed/*.csv) into the database.
# Runs as deskville_owner with the tenant set, exactly like the application:
# tenant_id is filled by its default (app.current_tenant()) and checked by the
# RLS policy. PostgreSQL refuses COPY into a table with RLS, so the CSV goes into
# a temporary table first (no RLS, gone at commit) and then INSERT ... SELECT,
# which the policy checks row by row.
# Replaces that tenant's seeded rows each run (TEST-* rows from the isolation
# suite are left alone). Tunnel must be up and migrations applied.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
seed="$(cd "$here/../db/seed" && pwd)"
PSQL="${PSQL:-$here/db-psql.sh}"   # override for a local test database

# Each council has its own reference format. RLS guarantees rows land in the tenant
# that is set; it cannot know the file was the wrong one. This prefix check can:
# loading Bury's file under Wigan fails and rolls back.
declare -A PREFIX=( [wigan]='WGN-%' [bury]='BRY/%' )
declare -A TENANT=(
  [wigan]=0000000a-0000-4000-8000-00000000000a
  [bury]=0000000b-0000-4000-8000-00000000000b
)

for t in wigan bury; do
  csv="$seed/service_requests_$t.csv"
  [ -f "$csv" ] || { echo "missing $csv (run scripts/gen-service-requests.py)"; exit 1; }
  "$PSQL" -X -q -v ON_ERROR_STOP=1 <<SQL
SET ROLE deskville_owner;
BEGIN;
SELECT set_config('app.tenant_id', '${TENANT[$t]}', true) \g /dev/null
CREATE TEMP TABLE incoming (reference text, category text, status text, area text,
  description text, created_at timestamptz, updated_at timestamptz, doc_id text) ON COMMIT DROP;
\copy incoming FROM '$csv' WITH (FORMAT csv, HEADER true)
DELETE FROM app.service_requests
  WHERE tenant_id = '${TENANT[$t]}' AND reference NOT LIKE 'TEST-%';
INSERT INTO app.service_requests (reference, category, status, area, description, created_at, updated_at, doc_id)
  SELECT reference, category, status, area, description, created_at, updated_at, doc_id FROM incoming;
DO \$\$ BEGIN
  IF EXISTS (SELECT 1 FROM app.service_requests
             WHERE reference NOT LIKE 'TEST-%' AND reference NOT LIKE '${PREFIX[$t]}') THEN
    RAISE EXCEPTION 'wrong file for tenant %: references must match %', '$t', '${PREFIX[$t]}';
  END IF;
END \$\$;
COMMIT;
RESET ROLE;
SQL
  echo "loaded $t"
done

echo "== counts, each read with its own tenant set (as deskville_owner, RLS forced)"
for t in wigan bury; do
  "$PSQL" -X -q -At -v ON_ERROR_STOP=1 <<SQL
SET ROLE deskville_owner;
BEGIN;
SELECT set_config('app.tenant_id', '${TENANT[$t]}', true) \g /dev/null
SELECT '$t: ' || count(*) FILTER (WHERE reference NOT LIKE 'TEST-%') || ' seeded requests, '
       || count(*) FILTER (WHERE reference LIKE 'WGN-%') || ' WGN refs, '
       || count(*) FILTER (WHERE reference LIKE 'BRY/%') || ' BRY refs'
  FROM app.service_requests;
COMMIT;
SQL
done
