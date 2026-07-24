#!/usr/bin/env python3
"""Local HTTP server that wraps the Lambda ``handler`` (default :8787).

Vite proxies ``/api`` → this process. Paths may arrive as ``/api/trips`` or ``/trips``.

Usage:
  cd backend
  export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
  # DynamoDB Local (required for create/propose persistence):
  #   docker compose up -d && uv run python scripts/create_local_table.py
  uv run python scripts/local_api.py
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _prepare_local_dynamodb() -> None:
    """Point at DynamoDB Local and ensure trip + metrics tables exist."""
    os.environ.setdefault("DYNAMODB_ENDPOINT", "http://127.0.0.1:8000")
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "vacation-planner-local-table")
    os.environ.setdefault("DYNAMODB_METRICS_TABLE_NAME", "vacation-planner-local-metrics")
    os.environ.setdefault("AWS_REGION", "us-east-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    # DynamoDB Local accepts any keys. Do not invent dummy keys when a real
    # credential chain exists — AgentCore InvokeAgentRuntime needs real AWS auth.
    has_chain = bool(
        os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
        or os.environ.get("AWS_SESSION_TOKEN")
    )
    if not has_chain:
        aws_dir = Path.home() / ".aws"
        has_chain = (aws_dir / "credentials").is_file() or (aws_dir / "config").is_file()
    if not has_chain:
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")

    from botocore.exceptions import EndpointConnectionError
    from db.client import get_dynamodb_client, metrics_table_name, reset_clients, table_name
    from db.schema import ensure_metrics_table, ensure_table

    reset_clients()
    name = table_name()
    metrics_name = metrics_table_name()
    endpoint = os.environ["DYNAMODB_ENDPOINT"]
    try:
        client = get_dynamodb_client()
        ensure_table(client, name, enable_ttl=False)
        ensure_metrics_table(client, metrics_name)
    except EndpointConnectionError:
        print(
            "local_api: cannot reach DynamoDB Local at "
            f"{endpoint}\n"
            "  Start it, then re-run:\n"
            "    docker compose up -d\n"
            "    uv run python scripts/create_local_table.py\n"
            f"  (working dir: {ROOT})",
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    except Exception as exc:  # noqa: BLE001 — startup boundary
        print(
            f"local_api: DynamoDB setup failed ({type(exc).__name__}: {exc})\n"
            "  Check DYNAMODB_ENDPOINT / table, or:\n"
            "    docker compose up -d\n"
            "    uv run python scripts/create_local_table.py",
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    print(f"local_api: DynamoDB ok — {name} @ {endpoint}", flush=True)
    print(f"local_api: metrics table ok — {metrics_name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Lambda HTTP adapter")
    parser.add_argument("--host", default=os.getenv("LOCAL_API_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("LOCAL_API_PORT", "8787")),
    )
    args = parser.parse_args()

    # Fail closed defaults match production; local must opt into AUTH_MODE=dev.
    if os.getenv("AUTH_MODE", "cognito").strip().lower() != "dev":
        print(
            "local_api: set AUTH_MODE=dev (got "
            f"{os.getenv('AUTH_MODE', 'cognito')!r}) so forgeable X-Dev-User-Sub works",
            file=sys.stderr,
        )
        return 2

    _prepare_local_dynamodb()

    from db.client import reset_clients
    from handler import handler
    from local_http import make_request_handler

    reset_clients()
    handler_cls = make_request_handler(handler)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(
        f"local_api: http://{args.host}:{args.port}  "
        f"(AUTH_MODE={os.environ['AUTH_MODE']} CREW_MODE={os.getenv('CREW_MODE', 'fake')})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nlocal_api: stopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
