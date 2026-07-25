"""Load optional API keys from Secrets Manager into process env (AgentCore)."""

from __future__ import annotations

import json
import os
from typing import Iterable


def _parse_secret_string(
    raw: str,
    *,
    preferred_keys: Iterable[str],
) -> str:
    value = raw.strip()
    if not value:
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, dict):
        for key in preferred_keys:
            cand = parsed.get(key)
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    return value


def ensure_env_from_secret(
    *,
    plain_env: str,
    arn_env: str,
    preferred_keys: Iterable[str],
    alt_plain_envs: Iterable[str] = (),
) -> str:
    """Return plaintext key; if unset, fetch ARN secret and set ``plain_env``."""
    existing = os.getenv(plain_env, "").strip()
    if existing:
        return existing
    for alt in alt_plain_envs:
        alt_val = os.getenv(alt, "").strip()
        if alt_val:
            os.environ[plain_env] = alt_val
            return alt_val

    secret_id = os.getenv(arn_env, "").strip()
    if not secret_id:
        return ""
    try:
        import boto3
    except ImportError:
        return ""
    try:
        raw = (
            boto3.client("secretsmanager")
            .get_secret_value(SecretId=secret_id)
            .get("SecretString")
            or ""
        )
    except Exception:
        return ""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    value = _parse_secret_string(raw, preferred_keys=preferred_keys)
    if value:
        os.environ[plain_env] = value
    return value


def ensure_serper_api_key() -> str:
    return ensure_env_from_secret(
        plain_env="SERPER_API_KEY",
        arn_env="SERPER_SECRET_ARN",
        preferred_keys=("api_key", "SERPER_API_KEY", "key", "value", "secret"),
    )


def ensure_amap_web_key() -> str:
    return ensure_env_from_secret(
        plain_env="AMAP_WEB_KEY",
        arn_env="AMAP_WEB_SECRET_ARN",
        preferred_keys=("api_key", "AMAP_WEB_KEY", "AMAP_KEY", "key", "value", "secret"),
        alt_plain_envs=("AMAP_KEY",),
    )
