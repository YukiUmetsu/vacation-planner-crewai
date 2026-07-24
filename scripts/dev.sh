#!/usr/bin/env bash
# One-command local stack: DynamoDB Local + API :8787 + Vite :5173 (live mode).
#
# Usage (from anywhere):
#   /Users/yukiumetsu/Documents/projects/udemy/travel-plan/vacation_planner/scripts/dev.sh
#   # or from repo root:
#   ./scripts/dev.sh
#
# Requires: Docker Desktop, uv, npm
# Ctrl+C stops the API and Vite (DynamoDB container stays up).
# Re-running frees :8787 / :5173 first so restarts never hit "Address already in use".

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
FRONTEND="${ROOT}/frontend"

API_PORT="${API_PORT:-8787}"
FE_PORT="${FE_PORT:-5173}"
API_PID=""
FE_PID=""

log() { printf 'dev: %s\n' "$*"; }

# Kill whatever is LISTENing on a TCP port (orphans from a prior crash / bad Ctrl+C).
free_listen_port() {
  local port="$1"
  local pids=""
  local attempt

  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi

  for attempt in 1 2 3; do
    pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -z "${pids}" ]]; then
      return 0
    fi
    if [[ "${attempt}" -eq 1 ]]; then
      log "port ${port} busy (pid ${pids//$'\n'/ }) — stopping…"
    fi
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.25
    pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -z "${pids}" ]]; then
      return 0
    fi
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
    sleep 0.15
  done

  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "error: could not free port ${port}" >&2
    exit 1
  fi
}

cleanup() {
  log "stopping API and Vite…"
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FE_PID}" ]] && kill -0 "${FE_PID}" 2>/dev/null; then
    kill "${FE_PID}" 2>/dev/null || true
  fi
  # uv/npm children can outlive the tracked PID and keep the socket.
  free_listen_port "${API_PORT}"
  free_listen_port "${FE_PORT}"
  wait 2>/dev/null || true
  log "stopped (DynamoDB container left running — docker compose -f ${BACKEND}/docker-compose.yml down to stop it)"
}

trap cleanup EXIT INT TERM

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

require_cmd docker
require_cmd uv
require_cmd npm
require_cmd lsof

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker is not running — start Docker Desktop and retry" >&2
  exit 1
fi

log "freeing :${API_PORT} and :${FE_PORT} if needed…"
free_listen_port "${API_PORT}"
free_listen_port "${FE_PORT}"

log "starting DynamoDB Local…"
docker compose -f "${BACKEND}/docker-compose.yml" up -d

export DYNAMODB_ENDPOINT="${DYNAMODB_ENDPOINT:-http://127.0.0.1:8000}"
export DYNAMODB_TABLE_NAME="${DYNAMODB_TABLE_NAME:-vacation-planner-local-table}"
export DYNAMODB_METRICS_TABLE_NAME="${DYNAMODB_METRICS_TABLE_NAME:-vacation-planner-local-metrics}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AUTH_MODE="${AUTH_MODE:-dev}"
export CREW_MODE="${CREW_MODE:-fake}"
export SAFETY_MODE="${SAFETY_MODE:-off}"
# Local: allow the default X-Dev-User-Sub so /metrics works without Cognito.
export METRICS_ADMIN_SUBS="${METRICS_ADMIN_SUBS:-local-dev-user}"

# DynamoDB Local accepts any credentials. Prefer the real AWS credential chain
# (~/.aws/credentials, AWS_PROFILE, env keys) so AgentCore can InvokeAgentRuntime.
# Only invent dummy keys when nothing else is available.
_has_aws_chain=false
if [[ -n "${AWS_ACCESS_KEY_ID:-}" || -n "${AWS_PROFILE:-}" || -n "${AWS_SESSION_TOKEN:-}" ]]; then
  _has_aws_chain=true
elif [[ -f "${HOME}/.aws/credentials" || -f "${HOME}/.aws/config" ]]; then
  _has_aws_chain=true
fi

if [[ "${_has_aws_chain}" == true ]]; then
  log "using AWS credential chain (env/profile/~/.aws) for AgentCore + DynamoDB Local"
else
  export AWS_ACCESS_KEY_ID=local
  export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-local}"
  log "no AWS credential chain found — dummy keys for DynamoDB Local only (AgentCore will fail auth)"
fi
unset _has_aws_chain

# Prefer an explicit export; otherwise load the deployed runtime from Terraform.
if [[ -z "${AGENT_RUNTIME_ARN:-}" ]] && command -v terraform >/dev/null 2>&1; then
  if arn="$(
    cd "${ROOT}/infra" && terraform output -raw agent_runtime_arn 2>/dev/null
  )" && [[ -n "${arn}" && "${arn}" == arn:* ]]; then
    export AGENT_RUNTIME_ARN="${arn}"
    log "loaded AGENT_RUNTIME_ARN from terraform output"
  fi
fi

if [[ -n "${AGENT_RUNTIME_ARN:-}" ]]; then
  log "AGENT_RUNTIME_ARN is set — UI AgentCore switch can invoke the runtime"
else
  log "AGENT_RUNTIME_ARN unset — UI AgentCore switch returns agent_misconfigured until set"
fi

# Google Places (photo enrich + /places/photo). Prefer plaintext key; else SM ARN from TF.
if [[ -z "${GOOGLE_PLACES_API_KEY:-}" && -z "${GOOGLE_PLACES_SECRET_ARN:-}" ]] \
  && command -v terraform >/dev/null 2>&1; then
  if places_arn="$(
    cd "${ROOT}/infra" && terraform output -raw google_places_secret_arn 2>/dev/null
  )" && [[ -n "${places_arn}" && "${places_arn}" == arn:* ]]; then
    export GOOGLE_PLACES_SECRET_ARN="${places_arn}"
    log "loaded GOOGLE_PLACES_SECRET_ARN from terraform output"
  fi
fi

if [[ -n "${GOOGLE_PLACES_API_KEY:-}" ]]; then
  log "GOOGLE_PLACES_API_KEY is set — Places enrich + photo resolve enabled"
elif [[ -n "${GOOGLE_PLACES_SECRET_ARN:-}" ]]; then
  log "GOOGLE_PLACES_SECRET_ARN is set — Places key loaded from Secrets Manager at runtime"
else
  log "GOOGLE_PLACES unset — place photos will 404 until you export GOOGLE_PLACES_API_KEY or set the SM secret"
fi

# Wait briefly for the port, then ensure the table exists.
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null -m 1 "http://127.0.0.1:8000/" 2>/dev/null || \
     curl -s -o /dev/null -m 1 -w '' "http://127.0.0.1:8000/" 2>/dev/null; then
    break
  fi
  sleep 0.3
done

log "ensuring DynamoDB table…"
(
  cd "${BACKEND}"
  uv run python scripts/create_local_table.py
)

log "starting API on http://127.0.0.1:${API_PORT} …"
(
  cd "${BACKEND}"
  # exec so the tracked PID is the server process (not a leftover shell).
  exec uv run python scripts/local_api.py --port "${API_PORT}"
) &
API_PID=$!

log "starting Vite on http://127.0.0.1:${FE_PORT} (live mode)…"
(
  cd "${FRONTEND}"
  if [[ ! -d node_modules ]]; then
    log "npm install (first run)…"
    npm install
  fi
  export VITE_USE_DEMO_DATA=false
  # Leave Cognito unset so DEV uses X-Dev-User-Sub against AUTH_MODE=dev
  exec npm run dev -- --host 127.0.0.1 --port "${FE_PORT}"
) &
FE_PID=$!

log "ready — open http://127.0.0.1:${FE_PORT}  (Ctrl+C to stop API + Vite)"
wait
