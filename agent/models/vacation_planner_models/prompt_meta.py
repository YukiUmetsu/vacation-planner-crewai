"""Prompt version + content hash for crew invocation metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Bump when day_plan / suggest_place / city_route prompts or agent backstories change.
PROMPT_VERSIONS: dict[str, str] = {
    "day_plan": "2026-07-24.1",
    "city_route": "2026-07-24.0",
    "suggest_place": "2026-07-24.1",
}


def prompt_hash_for_crew(crew_dir: Path) -> str:
    """Stable short hash of crew.jsonc + agents/*.jsonc (order-independent)."""
    parts: list[bytes] = []
    crew_file = crew_dir / "crew.jsonc"
    if crew_file.is_file():
        parts.append(crew_file.read_bytes())
    agents_dir = crew_dir / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.jsonc")):
            parts.append(path.name.encode() + b"\0" + path.read_bytes())
    digest = hashlib.sha256(b"\n".join(parts)).hexdigest()
    return digest[:12]
