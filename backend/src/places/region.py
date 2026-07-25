"""Destination / overnight region helpers (provider selection)."""

from __future__ import annotations

import re

# Mainland China markers. HK / Macau / Taiwan stay on Google.
_MAINLAND_EXPLICIT = re.compile(
    r"(?:"
    r"\bchina\b|\bprc\b|\bcn\b|"
    r"中国|中國|内地|大陸|大陆|"
    r"people'?s\s+republic\s+of\s+china"
    r")",
    re.IGNORECASE,
)

_NOT_MAINLAND = re.compile(
    r"(?:"
    r"hong\s*kong|\bhk\b|香港|"
    r"macau|macao|澳門|澳门|"
    r"taiwan|台灣|台湾|\btw\b"
    r")",
    re.IGNORECASE,
)

# Common mainland city / province names (Latin + common pinyin).
_MAINLAND_CITY = re.compile(
    r"(?:"
    r"beijing|shanghai|guangzhou|shenzhen|chengdu|hangzhou|chongqing|"
    r"wuhan|xian|xi'?an|nanjing|suzhou|tianjin|qingdao|dalian|xiamen|"
    r"kunming|changsha|zhengzhou|harbin|shenyang|jinan|fuzhou|ningbo|"
    r"hefei|nanchang|guiyang|nanning|haikou|sanya|lhasa|urumqi|"
    r"guilin|yangshuo|huangshan|suzhou|"
    r"北京|上海|广州|廣州|深圳|成都|杭州|重庆|重慶|武汉|武漢|西安|"
    r"南京|苏州|蘇州|天津|青岛|青島|大连|大連|厦门|廈門|昆明|长沙|長沙"
    r")",
    re.IGNORECASE,
)


def is_mainland_china(*texts: str | None) -> bool:
    """True when any text clearly refers to mainland China (not HK/Macau/Taiwan)."""
    blob = " ".join(str(t or "").strip() for t in texts if t)
    if not blob.strip():
        return False
    if _NOT_MAINLAND.search(blob):
        # Explicit SAR/Taiwan wins even if "China" also appears ("Hong Kong, China").
        return False
    if _MAINLAND_EXPLICIT.search(blob):
        return True
    return bool(_MAINLAND_CITY.search(blob))
