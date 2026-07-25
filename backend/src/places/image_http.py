"""Shared HTTP helpers for public place-image fallbacks."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from places.client import PlacesTransientError, raise_if_http_transient

logger = logging.getLogger(__name__)

UA = "VacationPlanner/1.0 (place photo fallback; local-dev)"
TIMEOUT_SEC = 6.0
MAX_BYTES = 900_000

OnTransient = Callable[[], None]


def http_get_json(
    url: str,
    *,
    what: str,
    on_transient: OnTransient | None = None,
) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raise_if_http_transient(exc, what=what)
        except PlacesTransientError:
            if on_transient:
                on_transient()
            raise
        logger.info("%s request failed: %s", what, exc)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise_if_http_transient(exc, what=what)
        logger.info("%s request failed: %s", what, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("%s unexpected error: %s", what, exc)
        return None
    return payload if isinstance(payload, dict) else None


def http_get_bytes(
    url: str,
    *,
    what: str,
    on_transient: OnTransient | None = None,
) -> tuple[bytes, str] | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = resp.read()
            if not data:
                return None
            content_type = (
                str(resp.headers.get("Content-Type") or "").split(";")[0].strip()
                or "image/jpeg"
            )
            if not content_type.startswith("image/"):
                return None
            return data, content_type
    except urllib.error.HTTPError as exc:
        try:
            raise_if_http_transient(exc, what=what)
        except PlacesTransientError:
            if on_transient:
                on_transient()
            raise
        logger.info("%s fetch failed: %s", what, exc)
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise_if_http_transient(exc, what=what)
        logger.info("%s fetch failed: %s", what, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("%s unexpected error: %s", what, exc)
        return None


def empty_photo_payload() -> dict[str, str | None]:
    return {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }


def payload_from_image_url(
    url: str,
    *,
    include_bytes: bool,
    what: str,
    on_transient: OnTransient | None = None,
    skip_bytes: bool = False,
) -> dict[str, str | None]:
    """Build the Places photo payload shape from a public image URL."""
    raw = str(url or "").strip()
    if not raw.startswith("http"):
        return empty_photo_payload()
    out: dict[str, str | None] = {
        "photo_url": raw,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    if not include_bytes or skip_bytes:
        return out
    fetched = http_get_bytes(raw, what=what, on_transient=on_transient)
    if fetched is None:
        return out
    data, content_type = fetched
    if len(data) <= MAX_BYTES:
        b64 = base64.b64encode(data).decode("ascii")
        out["photo_data_url"] = f"data:{content_type};base64,{b64}"
    return out
