"""Lambda-friendly logging setup so WARNING/ERROR always reach CloudWatch."""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotent: set root level from LOG_LEVEL (default INFO)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(levelname)s %(name)s %(message)s",
        )
    else:
        for handler in root.handlers:
            handler.setLevel(level)
    _CONFIGURED = True
