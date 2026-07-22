# AgentCore Runtime image for Vacation Planner crews.
# Build from the agent/ directory:
#   docker build -t vacation-planner-agent:latest .
#
# Runtime layout must keep crews/ next to crew_kickoff.py (see pyproject.toml).
# ADOT is opt-in via AGENT_OBSERVABILITY_ENABLED (set by Terraform when
# enable_genai_observability=true); see entrypoint.sh.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    CREWAI_DISABLE_TELEMETRY=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Dependency metadata first for layer caching.
COPY pyproject.toml uv.lock ./
COPY models ./models

# Entrypoint + crew assets (.dockerignore strips .venv, Phoenix, smoke tests, evals).
COPY main.py crew_kickoff.py invoke_payload.py entrypoint.sh ./
COPY crews/day_plan ./crews/day_plan
COPY crews/city_route ./crews/city_route
COPY crews/suggest_place ./crews/suggest_place

RUN chmod +x /app/entrypoint.sh \
    && uv sync --frozen --no-dev \
    && test -f /app/crews/day_plan/crew.jsonc \
    && test -f /app/crews/city_route/crew.jsonc \
    && test -f /app/crews/suggest_place/crew.jsonc \
    && test -f /app/crews/day_plan/day_models.py \
    && test -f /app/crews/city_route/city_models.py \
    && test -f /app/crews/suggest_place/suggest_models.py

CMD ["./entrypoint.sh"]
