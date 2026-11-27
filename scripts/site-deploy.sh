#!/usr/bin/env bash
# LAPTOP. Layer 7: publish site/ to the private site bucket and refresh CloudFront.
# config.js is written here from Terraform outputs (public values: API address,
# login domain, app client id), never committed with real values.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
out() { terraform -chdir="$ROOT/infra/foundation" output -raw "$1"; }
BUCKET=$(out site_bucket); DIST=$(out site_distribution_id)
CLIENT=$(out cognito_app_client_id); LOGIN=$(out login_domain)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cp -r "$ROOT/site/." "$TMP/"
cat > "$TMP/config.js" <<JS
export const CONFIG = { api: "https://api.deskville.co.uk", loginDomain: "$LOGIN", clientId: "$CLIENT" };
JS
# Short cache for the page and its code, a long one for the fonts.
aws s3 sync "$TMP/" "s3://$BUCKET/" --delete --exclude "fonts/*" --cache-control "max-age=60" --no-progress
aws s3 sync "$TMP/fonts/" "s3://$BUCKET/fonts/" --delete --cache-control "max-age=31536000, immutable" --no-progress
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --no-cli-pager \
  --query 'Invalidation.Status' --output text
echo "published to $(terraform -chdir="$ROOT/infra/foundation" output -json site_urls | tr -d '[]"\n ' | tr ',' ' ')"
