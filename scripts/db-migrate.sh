#!/usr/bin/env bash
# LAPTOP. Applies db/migrations/*.sql in order, each in its own transaction,
# as the master user through the tunnel. Already-applied files are skipped,
# so running it twice is safe.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
migrations="$here/../db/migrations"

master() { "$here/db-psql.sh" -X -q -v ON_ERROR_STOP=1 "$@"; }

master -c "CREATE TABLE IF NOT EXISTS public.deskville_migrations (
             version    text PRIMARY KEY,
             applied_at timestamptz NOT NULL DEFAULT now())"

for f in "$migrations"/*.sql; do
  v="$(basename "$f" .sql)"
  if [ "$(master -At -c "SELECT 1 FROM public.deskville_migrations WHERE version = '$v'")" = "1" ]; then
    echo "skip   $v"
    continue
  fi
  master --single-transaction -f "$f" -c "INSERT INTO public.deskville_migrations (version) VALUES ('$v')"
  echo "apply  $v"
done
