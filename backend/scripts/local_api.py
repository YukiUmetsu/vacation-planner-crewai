#!/usr/bin/env python3
"""Local HTTP server that wraps the Lambda ``handler`` (default :8787).

Vite proxies ``/api`` → this process. Paths may arrive as ``/api/trips`` or ``/trips``.

Usage:
  cd backend
  export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
  # Optional DynamoDB Local:
  #   docker compose up -d && uv run python scripts/create_local_table.py
  #   export DYNAMODB_ENDPOINT=http://localhost:8000
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
