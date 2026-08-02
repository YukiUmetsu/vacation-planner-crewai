"""Strip risky markdown/HTML links from AI prose before persist (exfil mitigation)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Hosts we already use for place maps / enrichment.
_ALLOWED_HOST_SUFFIXES = (
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "maps.app.goo.gl",
    "goo.gl",
    "amap.com",
    "gaode.com",
    "autonavi.com",
)

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_RAW_URL = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _host_allowed(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    if not h:
        return False
    for suffix in _ALLOWED_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def _url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return _host_allowed(parsed.netloc.split("@")[-1])


def sanitize_url_field(url: str | None) -> str | None:
    """Keep allowlisted map/site URLs; drop everything else (exfil / phishing)."""
    if url is None:
        return None
    raw = str(url).strip()
    if not raw:
        return ""
    return raw if _url_allowed(raw) else ""


def sanitize_ai_prose(text: str) -> str:
    """Remove markdown images and non-allowlisted links; strip HTML/control chars."""
    if not text:
        return text

    def _replace_md_link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2).strip()
        if _url_allowed(url):
            return match.group(0)
        return label or ""

    out = _MD_IMAGE.sub("", text)
    out = _MD_LINK.sub(_replace_md_link, out)

    def _replace_raw(match: re.Match[str]) -> str:
        url = match.group(0)
        return url if _url_allowed(url) else ""

    out = _RAW_URL.sub(_replace_raw, out)
    out = _HTML_TAG.sub("", out)
    out = _CONTROL.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def sanitize_mapping(fields: dict[str, str]) -> dict[str, str]:
    return {key: sanitize_ai_prose(value) for key, value in fields.items()}


def sanitize_place_dict(place: dict[str, Any]) -> dict[str, Any]:
    """Sanitize traveler-visible string fields on a place payload (copy)."""
    out = dict(place)
    for key in (
        "name",
        "reason_to_visit",
        "reason",
        "summary",
        "description",
        "details",
    ):
        if isinstance(out.get(key), str):
            out[key] = sanitize_ai_prose(out[key])
    for key in ("maps_url", "map_url", "website_url"):
        if key in out and out.get(key) is not None:
            out[key] = sanitize_url_field(str(out.get(key) or ""))
    return out


def sanitize_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [sanitize_place_dict(p) if isinstance(p, dict) else p for p in places]
