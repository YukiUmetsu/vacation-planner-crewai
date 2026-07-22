#!/usr/bin/env bash
# Build and push the AgentCore runtime image to ECR.
#
# Usage (from repo root or agent/):
#   export AWS_REGION=us-east-1
#   export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
#   export IMAGE_TAG=latest
#   ./scripts/build_push_image.sh
#
# Then set:
#   export TF_VAR_agent_runtime_container_uri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/vacation-planner-agent:${IMAGE_TAG}"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE_NAME="${IMAGE_NAME:-vacation-planner-agent}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}:${IMAGE_TAG}"
REPO_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} from ${AGENT_DIR}"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" "${AGENT_DIR}"

echo "Ensuring ECR repository ${IMAGE_NAME} exists"
aws ecr describe-repositories --repository-names "${IMAGE_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${IMAGE_NAME}" --region "${AWS_REGION}" >/dev/null

echo "Logging in to ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Tagging and pushing ${ECR_URI}"
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_URI}"
docker push "${ECR_URI}"

echo "Pushed: ${ECR_URI}"
echo "Set TF_VAR_agent_runtime_container_uri=${ECR_URI}"
