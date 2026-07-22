#!/bin/sh
# Observability is off by default. AgentCore Terraform sets
# AGENT_OBSERVABILITY_ENABLED=true (and ADOT env) when enable_genai_observability is on.
set -eu

if [ "${AGENT_OBSERVABILITY_ENABLED:-false}" = "true" ]; then
  exec uv run --no-sync opentelemetry-instrument python main.py
fi

exec uv run --no-sync python main.py
