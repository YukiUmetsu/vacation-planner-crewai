#!/usr/bin/env bash
# Sync Cognito Google/Facebook IdPs from Secrets Manager (keeps secrets out of Terraform state).
#
# Usage (from repo root or infra/):
#   ./infra/scripts/sync_cognito_idps_from_secrets.sh
#
# Requires: aws CLI, jq, terraform outputs (or env overrides).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

require_cmd aws
require_cmd jq
require_cmd terraform

tf_out() {
  terraform -chdir="${INFRA_DIR}" output -raw "$1"
}

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_REGION="${REGION}"
export AWS_DEFAULT_REGION="${REGION}"

POOL_ID="${COGNITO_USER_POOL_ID:-$(tf_out cognito_user_pool_id)}"
GOOGLE_SECRET="${COGNITO_GOOGLE_SECRET_NAME:-$(tf_out cognito_google_secret_name)}"
FACEBOOK_SECRET="${COGNITO_FACEBOOK_SECRET_NAME:-$(tf_out cognito_facebook_secret_name)}"

echo "sync_cognito_idps: pool=${POOL_ID}"
echo "sync_cognito_idps: google_secret=${GOOGLE_SECRET}"
echo "sync_cognito_idps: facebook_secret=${FACEBOOK_SECRET}"

get_secret_string() {
  aws secretsmanager get-secret-value \
    --secret-id "$1" \
    --query SecretString \
    --output text 2>/dev/null || true
}

upsert_google() {
  local raw client_id client_secret
  raw="$(get_secret_string "${GOOGLE_SECRET}")"
  if [[ -z "${raw}" || "${raw}" == "None" ]]; then
    echo "sync_cognito_idps: skip Google (secret empty or missing)"
    return 0
  fi
  client_id="$(jq -r '.client_id // empty' <<<"${raw}")"
  client_secret="$(jq -r '.client_secret // empty' <<<"${raw}")"
  if [[ -z "${client_id}" || -z "${client_secret}" ]]; then
    echo "sync_cognito_idps: skip Google (JSON needs client_id and client_secret)" >&2
    return 0
  fi

  local details
  details="$(jq -nc \
    --arg id "${client_id}" \
    --arg secret "${client_secret}" \
    '{client_id:$id, client_secret:$secret, authorize_scopes:"openid email profile", attributes_url_add_attributes:"true"}')"

  if aws cognito-idp describe-identity-provider \
    --user-pool-id "${POOL_ID}" \
    --provider-name Google >/dev/null 2>&1; then
    echo "sync_cognito_idps: updating Google IdP"
    aws cognito-idp update-identity-provider \
      --user-pool-id "${POOL_ID}" \
      --provider-name Google \
      --provider-details "${details}" \
      --attribute-mapping email=email,username=sub \
      >/dev/null
  else
    echo "sync_cognito_idps: creating Google IdP"
    aws cognito-idp create-identity-provider \
      --user-pool-id "${POOL_ID}" \
      --provider-name Google \
      --provider-type Google \
      --provider-details "${details}" \
      --attribute-mapping email=email,username=sub \
      >/dev/null
  fi
}

upsert_facebook() {
  local raw app_id app_secret
  raw="$(get_secret_string "${FACEBOOK_SECRET}")"
  if [[ -z "${raw}" || "${raw}" == "None" ]]; then
    echo "sync_cognito_idps: skip Facebook (secret empty or missing)"
    return 0
  fi
  app_id="$(jq -r '.app_id // .client_id // empty' <<<"${raw}")"
  app_secret="$(jq -r '.app_secret // .client_secret // empty' <<<"${raw}")"
  if [[ -z "${app_id}" || -z "${app_secret}" ]]; then
    echo "sync_cognito_idps: skip Facebook (JSON needs app_id and app_secret)" >&2
    return 0
  fi

  local details
  details="$(jq -nc \
    --arg id "${app_id}" \
    --arg secret "${app_secret}" \
    '{client_id:$id, client_secret:$secret, api_version:"v21.0", authorize_scopes:"public_profile, email"}')"

  if aws cognito-idp describe-identity-provider \
    --user-pool-id "${POOL_ID}" \
    --provider-name Facebook >/dev/null 2>&1; then
    echo "sync_cognito_idps: updating Facebook IdP"
    aws cognito-idp update-identity-provider \
      --user-pool-id "${POOL_ID}" \
      --provider-name Facebook \
      --provider-details "${details}" \
      --attribute-mapping email=email,name=name,preferred_username=id,username=id \
      >/dev/null
  else
    echo "sync_cognito_idps: creating Facebook IdP"
    aws cognito-idp create-identity-provider \
      --user-pool-id "${POOL_ID}" \
      --provider-name Facebook \
      --provider-type Facebook \
      --provider-details "${details}" \
      --attribute-mapping email=email,name=name,preferred_username=id,username=id \
      >/dev/null
  fi
}

upsert_google
upsert_facebook
echo "sync_cognito_idps: done"
