"""Resolve secrets from env plaintext or AWS Secrets Manager ARNs (runtime)."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def get_secret_string(secret_id: str) -> str:
    """Fetch SecretString for a Secrets Manager name or ARN. Cached per process."""
    sid = secret_id.strip()
    if not sid:
        return ""
    try:
        import boto3
    except ImportError:
        logger.warning("boto3 unavailable; cannot load secret %s", sid)
        return ""
    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=sid)
    except Exception as exc:  # noqa: BLE001 — soft fail for optional secrets
        logger.warning("GetSecretValue failed for %s: %s", sid, exc)
        return ""
    raw = resp.get("SecretString")
    if isinstance(raw, str):
        return raw
    return ""


def resolve_secret(
    *,
    plain_env: str,
    arn_env: str,
    json_key: str | None = None,
    fallback: str = "",
) -> str:
    """Prefer plaintext env (local), else Secrets Manager ARN/name env.

    If ``json_key`` is set, parse SecretString as JSON and return that key.
    """
    plain = os.getenv(plain_env, "").strip()
    if plain:
        return plain
    secret_id = os.getenv(arn_env, "").strip()
    if not secret_id:
        return fallback
    raw = get_secret_string(secret_id)
    if not raw:
        return fallback
    if json_key is None:
        # Plain string secret, or JSON with a single common key.
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()
        if isinstance(parsed, dict):
            for key in ("api_key", "key", "value", "secret"):
                val = parsed.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            return fallback
        return raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("secret %s is not JSON; cannot read key %s", arn_env, json_key)
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    val = parsed.get(json_key)
    return val.strip() if isinstance(val, str) else fallback
