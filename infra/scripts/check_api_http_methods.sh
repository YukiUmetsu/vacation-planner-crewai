#!/usr/bin/env bash
# Fail if the SPA uses an HTTP method that API Gateway CORS/routes do not allow.
#
# Root cause this guards: DELETE was implemented in Lambda + FE but omitted from
# aws_apigatewayv2_api.cors_configuration / api_http_methods → prod CORS errors.
#
# Prefer infra/scripts/validate.sh (runs this, then terraform validate).
# Usage:
#   ./infra/scripts/check_api_http_methods.sh
#   ./infra/scripts/validate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_TF="${ROOT}/infra/api/main.tf"
FE_API="${ROOT}/frontend/src/api"
HTTP_UTILS="${ROOT}/backend/src/http_utils.py"

if [[ ! -f "${API_TF}" ]]; then
  echo "error: missing ${API_TF}" >&2
  exit 1
fi

python3 - "${API_TF}" "${FE_API}" "${HTTP_UTILS}" <<'PY'
import re
import sys
from pathlib import Path

api_tf, fe_api, http_utils = map(Path, sys.argv[1:4])

text = api_tf.read_text()
m = re.search(r"api_http_methods\s*=\s*\[(.*?)\]", text, re.S)
if not m:
    raise SystemExit("api_http_methods not found in infra/api/main.tf")
tf_methods = set(re.findall(r'"([A-Z]+)"', m.group(1)))

fe_methods: set[str] = set()
for path in fe_api.rglob("*.ts"):
    if path.name.endswith(".test.ts"):
        continue
    for match in re.finditer(r"""method:\s*["']([A-Z]+)["']""", path.read_text()):
        method = match.group(1)
        if method != "OPTIONS":
            fe_methods.add(method)

print(f"check_api_http_methods: terraform={' '.join(sorted(tf_methods))}")
print(f"check_api_http_methods: frontend={' '.join(sorted(fe_methods))}")

missing = sorted(fe_methods - tf_methods)
failed = False
for method in missing:
    print(
        f"error: frontend uses {method} but infra/api/main.tf "
        f"api_http_methods does not include it",
        file=sys.stderr,
    )
    print(
        f'  → add "{method}" to local.api_http_methods '
        f"(CORS + JWT routes use that list)",
        file=sys.stderr,
    )
    failed = True

if http_utils.is_file():
    header_line = next(
        (
            line
            for line in http_utils.read_text().splitlines()
            if "access-control-allow-methods" in line
        ),
        "",
    )
    for method in sorted(tf_methods):
        if method not in header_line:
            print(
                f"error: backend http_utils Access-Control-Allow-Methods missing {method}",
                file=sys.stderr,
            )
            failed = True

if failed:
    raise SystemExit(1)
print("check_api_http_methods: ok")
PY
