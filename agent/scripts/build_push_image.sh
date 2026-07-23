#!/usr/bin/env bash
# Build and push the AgentCore runtime image to ECR.
#
# Default: bump agent/pyproject.toml patch version, tag the image as that
# version (e.g. 0.1.2). No :latest, no -dirty — Terraform always gets a new URI.
#
# Usage:
#   export AWS_REGION=us-east-1
#   ./scripts/build_push_image.sh
#
# Options:
#   BUMP=patch|minor|major   # default patch; ignored if IMAGE_TAG is set
#   IMAGE_TAG=0.2.0          # skip bump; use this tag / version as-is
#   SKIP_VERSION_BUMP=1      # keep current pyproject version as tag (no write)
#
# After push, apply infra with the printed URI:
#   export TF_VAR_agent_runtime_container_uri=...
#   cd ../infra && terraform apply

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${AGENT_DIR}/.." && pwd)"
PYPROJECT="${AGENT_DIR}/pyproject.toml"

AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE_NAME="${IMAGE_NAME:-vacation-planner-agent}"
BUMP="${BUMP:-patch}"

read_version() {
  python3 - <<'PY' "${PYPROJECT}"
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
if not m:
    raise SystemExit("could not read version from agent/pyproject.toml")
print(m.group(1))
PY
}

bump_version() {
  local level="${1}"
  python3 - <<'PY' "${PYPROJECT}" "${level}"
import re, sys
path, level = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
if not m:
    raise SystemExit("could not read version from agent/pyproject.toml")
parts = [int(p) for p in m.group(1).split(".")]
while len(parts) < 3:
    parts.append(0)
major, minor, patch = parts[0], parts[1], parts[2]
if level == "major":
    major, minor, patch = major + 1, 0, 0
elif level == "minor":
    minor, patch = minor + 1, 0
elif level == "patch":
    patch += 1
else:
    raise SystemExit(f"BUMP must be patch|minor|major, got {level!r}")
new = f"{major}.{minor}.{patch}"
text, n = re.subn(
    r'(?m)^version\s*=\s*"[^"]+"',
    f'version = "{new}"',
    text,
    count=1,
)
if n != 1:
    raise SystemExit("failed to write bumped version")
open(path, "w", encoding="utf-8").write(text)
print(new)
PY
}

PREV_VERSION="$(read_version)"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"

if [[ -n "${IMAGE_TAG:-}" ]]; then
  AGENT_VERSION="${IMAGE_TAG}"
  echo "Using IMAGE_TAG=${IMAGE_TAG} (no pyproject bump)"
elif [[ "${SKIP_VERSION_BUMP:-}" == "1" ]]; then
  AGENT_VERSION="${PREV_VERSION}"
  IMAGE_TAG="${AGENT_VERSION}"
  echo "SKIP_VERSION_BUMP=1 — tagging as ${IMAGE_TAG}"
else
  AGENT_VERSION="$(bump_version "${BUMP}")"
  IMAGE_TAG="${AGENT_VERSION}"
  echo "Bumped agent version ${PREV_VERSION} → ${AGENT_VERSION} (BUMP=${BUMP})"
  echo "Refreshing uv.lock for frozen Docker sync"
  (cd "${AGENT_DIR}" && uv lock)
fi

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  agent version: ${AGENT_VERSION}"
echo "  git sha:       ${GIT_SHA} (label/env only; not part of the tag)"
echo "  context:       ${AGENT_DIR}"

docker build \
  --build-arg "AGENT_VERSION=${AGENT_VERSION}" \
  --build-arg "GIT_SHA=${GIT_SHA}" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  "${AGENT_DIR}"

echo "Ensuring ECR repository ${IMAGE_NAME} exists"
aws ecr describe-repositories --repository-names "${IMAGE_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${IMAGE_NAME}" --region "${AWS_REGION}" >/dev/null

echo "Logging in to ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Tagging and pushing ${ECR_URI}"
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_URI}"
docker push "${ECR_URI}"

echo
echo "Pushed: ${ECR_URI}"
echo
echo "Deploy AgentCore with this tag:"
echo "  export TF_VAR_agent_runtime_container_uri=${ECR_URI}"
echo "  cd ${REPO_ROOT}/infra && terraform apply"
echo
echo "Commit the pyproject.toml version bump with your agent changes."
