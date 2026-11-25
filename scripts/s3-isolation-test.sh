#!/usr/bin/env bash
# LAPTOP. Proves tenant isolation at the storage layer (ABAC, D28).
# Assumes deskville-ingest with a session tag tenant=<council> and checks what
# that session can and cannot do in the content bucket. Read-only except one
# small probe object written to the session's own cache prefix.
# Exit code = number of failures (0 = all passed).
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tf="$here/../infra/foundation"
BUCKET="$(terraform -chdir="$tf" output -raw content_bucket)"
ROLE="$(terraform -chdir="$tf" output -raw ingest_role_arn)"
DOC="waste-collection-days.md"   # exists for every council
fails=0

assume() {  # assume <tenant-tag or empty> -> prints "AK SK TOKEN" or nothing
  local tags=()
  [ -n "$1" ] && tags=(--tags "Key=tenant,Value=$1")
  aws sts assume-role --role-arn "$ROLE" --role-session-name "isolation-test-${1:-none}" \
    "${tags[@]}" --duration-seconds 900 \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text 2>/dev/null
}

check() {  # check <expect ok|denied> <description> <command...>
  local expect="$1" desc="$2"; shift 2
  local out; out="$("$@" 2>&1)"; local rc=$?
  local got="ok"; [ $rc -ne 0 ] && got="denied"
  if [ "$got" = "$expect" ]; then printf "PASS  %-48s %s\n" "$desc" "$got"
  else printf "FAIL  %-48s expected %s, got %s: %s\n" "$desc" "$expect" "$got" "$(echo "$out" | tail -1)"; fails=$((fails+1)); fi
}

echo "== who may assume the role"
for t in "" leeds; do
  if [ -n "$(assume "$t")" ]; then printf "FAIL  %-48s %s\n" "assume with tenant='${t:-<none>}'" "allowed"; fails=$((fails+1))
  else printf "PASS  %-48s %s\n" "assume with tenant='${t:-<none>}'" "refused"; fi
done

for me in wigan bury; do
  other=bury; [ "$me" = bury ] && other=wigan
  read -r AK SK TK < <(assume "$me")
  [ -n "${AK:-}" ] || { echo "FAIL  could not assume as $me"; fails=$((fails+1)); continue; }
  as() { AWS_ACCESS_KEY_ID="$AK" AWS_SECRET_ACCESS_KEY="$SK" AWS_SESSION_TOKEN="$TK" aws "$@"; }
  echo "== session tenant=$me"
  check ok     "$me reads its own document"            as s3api head-object --bucket "$BUCKET" --key "$me/docs/$DOC"
  check ok     "$me lists its own prefix"              as s3api list-objects-v2 --bucket "$BUCKET" --prefix "$me/docs/" --max-items 1
  check ok     "$me writes to its own cache"           as s3api put-object --bucket "$BUCKET" --key "$me/cache/_isolation-probe" --body /dev/null
  check denied "$me cannot read $other's document"     as s3api head-object --bucket "$BUCKET" --key "$other/docs/$DOC"
  check denied "$me cannot list $other's prefix"       as s3api list-objects-v2 --bucket "$BUCKET" --prefix "$other/" --max-items 1
  check denied "$me cannot list the whole bucket"      as s3api list-objects-v2 --bucket "$BUCKET" --max-items 1
  check denied "$me cannot write to $other's cache"    as s3api put-object --bucket "$BUCKET" --key "$other/cache/_isolation-probe" --body /dev/null
  check denied "$me cannot write its own docs"         as s3api put-object --bucket "$BUCKET" --key "$me/docs/_probe.md" --body /dev/null
done

echo
[ $fails -eq 0 ] && echo "all storage isolation checks passed" || echo "$fails check(s) FAILED"
exit $fails
