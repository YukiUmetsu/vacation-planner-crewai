"""Stable place keys for cross-day dedupe."""

from __future__ import annotations

import re
import unicodedata


def normalize_place_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", " ", text)


def make_place_key(name: str, address: str | None = None) -> str:
    return f"{normalize_place_text(name)}|{normalize_place_text(address)}"
