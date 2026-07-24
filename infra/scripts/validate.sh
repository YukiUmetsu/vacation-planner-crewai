#!/usr/bin/env bash
# Local / deploy-time Terraform validation helpers.
#
# Runs SPA ↔ API Gateway HTTP method drift check, then `terraform validate`.
# Prefer this over bare `terraform validate` after infra or FE API client changes.
#
# Usage (from repo root or infra/):
#   ./infra/scripts/validate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA="${ROOT}/infra"

echo "validate: checking API HTTP methods (SPA ↔ API Gateway CORS/routes)…"
"${INFRA}/scripts/check_api_http_methods.sh"

echo "validate: terraform validate…"
cd "${INFRA}"
if [[ ! -d .terraform ]]; then
  echo "validate: .terraform missing — run 'terraform init' in infra/ first" >&2
  exit 1
fi
terraform validate
echo "validate: ok"
