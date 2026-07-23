#!/usr/bin/env bash
# Build the SPA with Cognito/API env from Terraform outputs, sync to S3, invalidate CloudFront.
#
# Usage (from anywhere):
#   ./frontend/scripts/deploy.sh
#
# Optional:
#   SKIP_INSTALL=1              # skip npm install
#   INFRA_DIR=...               # override path to infra/
#   ALLOW_BROKEN_COGNITO_URLS=1 # continue even if CloudFront callback/logout missing from Cognito
#
# Cognito must allow the CloudFront callback/logout URLs (script aborts if missing).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFRA_DIR="$(cd "${INFRA_DIR:-${FRONTEND_DIR}/../infra}" && pwd)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

tf_out() {
  terraform -chdir="${INFRA_DIR}" output -raw "$1"
}

require_cmd aws
require_cmd terraform
require_cmd npm

echo "deploy: reading Terraform outputs from ${INFRA_DIR}"
API_URL="$(tf_out api_endpoint)"
SITE_URL="$(tf_out frontend_site_url)"
BUCKET="$(tf_out frontend_bucket_name)"
DIST_ID="$(tf_out cloudfront_distribution_id)"
COGNITO_DOMAIN="$(tf_out cognito_hosted_ui_domain)"
COGNITO_CLIENT_ID="$(tf_out cognito_user_pool_client_id)"
COGNITO_POOL_ID="$(tf_out cognito_user_pool_id)"
# New output until `terraform apply` — fall back to COGNITO-only if missing from state.
if COGNITO_PROVIDERS="$(
  terraform -chdir="${INFRA_DIR}" output -json cognito_identity_providers 2>/dev/null \
    | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)))'
)"; then
  :
else
  echo "deploy: warning: cognito_identity_providers not in state yet — using COGNITO." >&2
  echo "  Run terraform apply (with this repo's infra/) then redeploy for Facebook/Google buttons." >&2
  COGNITO_PROVIDERS="COGNITO"
fi

# Strip trailing slash from site URL for consistent join
SITE_URL="${SITE_URL%/}"
CALLBACK_URL="${SITE_URL}/callback"
LOGOUT_URL="${SITE_URL}/"

export VITE_API_URL="${API_URL}"
export VITE_USE_DEMO_DATA=false
export VITE_COGNITO_DOMAIN="${COGNITO_DOMAIN}"
export VITE_COGNITO_CLIENT_ID="${COGNITO_CLIENT_ID}"
export VITE_COGNITO_REDIRECT_URI="${CALLBACK_URL}"
export VITE_COGNITO_LOGOUT_URI="${LOGOUT_URL}"
export VITE_COGNITO_IDENTITY_PROVIDERS="${COGNITO_PROVIDERS}"

echo "deploy: VITE_API_URL=${VITE_API_URL}"
echo "deploy: VITE_COGNITO_DOMAIN=${VITE_COGNITO_DOMAIN}"
echo "deploy: VITE_COGNITO_REDIRECT_URI=${VITE_COGNITO_REDIRECT_URI}"
echo "deploy: VITE_COGNITO_IDENTITY_PROVIDERS=${VITE_COGNITO_IDENTITY_PROVIDERS}"
echo "deploy: site=${SITE_URL}"

echo "deploy: checking Cognito allows CloudFront callback/logout"
CALLBACKS_JSON="$(
  aws cognito-idp describe-user-pool-client \
    --user-pool-id "${COGNITO_POOL_ID}" \
    --client-id "${COGNITO_CLIENT_ID}" \
    --query 'UserPoolClient.[CallbackURLs,LogoutURLs]' \
    --output json
)"
if ! python3 -c "
import json, sys
callbacks, logouts = json.loads(sys.argv[1])
cb, lo = sys.argv[2], sys.argv[3]
ok = cb in (callbacks or []) and lo in (logouts or [])
sys.exit(0 if ok else 1)
" "${CALLBACKS_JSON}" "${CALLBACK_URL}" "${LOGOUT_URL}"; then
  echo "warning: Cognito app client does not list CloudFront URLs yet." >&2
  echo "  Add these, then terraform apply:" >&2
  echo "    callback_urls += [\"${CALLBACK_URL}\"]" >&2
  echo "    logout_urls   += [\"${LOGOUT_URL}\"]" >&2
  echo "  Hosted UI login from CloudFront will fail until that is done." >&2
  if [[ "${ALLOW_BROKEN_COGNITO_URLS:-0}" == "1" ]]; then
    echo "deploy: ALLOW_BROKEN_COGNITO_URLS=1 — continuing despite Cognito URL mismatch." >&2
  else
    echo "deploy: aborting (set ALLOW_BROKEN_COGNITO_URLS=1 to override)." >&2
    exit 1
  fi
fi

cd "${FRONTEND_DIR}"
if [[ "${SKIP_INSTALL:-0}" != "1" ]]; then
  echo "deploy: npm install"
  npm install
fi

echo "deploy: npm run build"
npm run build

echo "deploy: syncing dist/ → s3://${BUCKET}/"
aws s3 sync dist/ "s3://${BUCKET}/" --delete

echo "deploy: invalidating CloudFront ${DIST_ID}"
INVALIDATION_ID="$(
  aws cloudfront create-invalidation \
    --distribution-id "${DIST_ID}" \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text
)"

echo "deploy: OK"
echo "  site:          ${SITE_URL}"
echo "  invalidation:  ${INVALIDATION_ID}"
echo "  privacy:       ${SITE_URL}/privacy.html"
echo "  data deletion: ${SITE_URL}/data-deletion.html"
echo "  (CloudFront may take 1–2 minutes to refresh)"
