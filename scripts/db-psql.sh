#!/usr/bin/env bash
# LAPTOP. psql as the master user through the tunnel (scripts/db-tunnel.sh first).
# The password goes from Secrets Manager straight into psql's environment:
# never printed, never written to disk. Extra arguments are passed to psql.
set -euo pipefail
cd "$(dirname "$0")/../infra/database"

secret_arn="$(terraform output -raw db_master_secret_arn)"
PGPASSWORD="$(aws secretsmanager get-secret-value --secret-id "$secret_arn" --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
export PGPASSWORD

exec psql "host=localhost port=15432 dbname=$(terraform output -raw db_name) user=$(terraform output -raw db_master_username) sslmode=require" "$@"
