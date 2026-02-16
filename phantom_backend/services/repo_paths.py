from __future__ import annotations

from pathlib import Path


def repo_root_for(game_key: str) -> Path:
    internal = Path(__file__).resolve().parents[1] / "games" / game_key
    return internal
