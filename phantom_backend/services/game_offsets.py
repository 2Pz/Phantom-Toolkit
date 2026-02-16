from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from phantom_backend.core.errors import PhantomError


@lru_cache(maxsize=8)
def load_manager_offsets(game_key: str) -> dict[str, Any]:
    """Load offsets from the internal games/{game}/offsets.toml."""
    path = Path(__file__).resolve().parents[1] / "games" / game_key / "offsets.toml"
    if path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8"))

    raise PhantomError(
        f"offsets.toml not found for {game_key} in internal games directory."
    )


def get_hex_int(d: dict[str, Any], *keys: str) -> int:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise PhantomError(f"Missing key in offsets.toml: {'.'.join(keys)}")
        cur = cur[k]
    if isinstance(cur, int):
        return cur
    if isinstance(cur, str):
        s = cur.strip().lower()
        if s.startswith("0x"):
            return int(s, 16)
        if s.isdigit():
            return int(s)
    raise PhantomError(f"Invalid int value at {'.'.join(keys)}: {cur!r}")
