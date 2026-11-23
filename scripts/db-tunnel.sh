#!/usr/bin/env bash
# LAPTOP. Opens localhost:15432 -> database:5432 through the SSM bastion.
# Runs in the background; log in /tmp/deskville-tunnel.log. Stop: scripts/db-tunnel.sh stop
set -euo pipefail
cd "$(dirname "$0")/../infra/database"

if [ "${1:-}" = "stop" ]; then
  pkill -f "AWS-StartPortForwardingSessionToRemoteHost.*15432" && echo "tunnel stopped" || echo "no tunnel running"
  exit 0
fi

bastion="$(terraform output -raw bastion_instance_id)"
host="$(terraform output -raw db_address)"

nohup aws ssm start-session --target "$bastion" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$host\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"15432\"]}" \
  > /tmp/deskville-tunnel.log 2>&1 &

for _ in $(seq 1 20); do
  if grep -q "Waiting for connections" /tmp/deskville-tunnel.log 2>/dev/null; then
    echo "tunnel up: localhost:15432 -> database:5432"
    exit 0
  fi
  sleep 1
done
echo "tunnel did not come up in 20 s; see /tmp/deskville-tunnel.log" >&2
exit 1
