#!/usr/bin/env bash
# Build a Lambda-ready package: backend/src + production deps (no CrewAI).
# Output: backend/.build/lambda/  (zipped by Terraform archive_file)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_ROOT="$ROOT/.build"
OUT="$BUILD_ROOT/lambda"
REQ="$BUILD_ROOT/requirements.txt"

echo "build_lambda: cleaning $OUT"
rm -rf "$OUT"
mkdir -p "$OUT"

echo "build_lambda: exporting production requirements"
cd "$ROOT"
uv export --no-dev --no-hashes --no-emit-project -o "$REQ"

echo "build_lambda: installing deps into package (Linux x86_64 / cp312 for Lambda)"
# Match infra/api Lambda runtime python3.12 (x86_64 default).
uv pip install \
  --target "$OUT" \
  --python-version 3.12 \
  --python-platform x86_64-manylinux2014 \
  --only-binary=:all: \
  -r "$REQ"

echo "build_lambda: copying application source"
# Source last so our modules win over any conflicting package names.
cp -R "$ROOT/src/." "$OUT/"

# Drop bytecode / tests if any leaked
find "$OUT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$OUT" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true

echo "build_lambda: OK → $OUT"
du -sh "$OUT" || true
