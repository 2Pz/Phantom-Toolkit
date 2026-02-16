from __future__ import annotations

from phantom_backend.games.base import GameAdapter
from phantom_backend.games.ds3.adapter import Ds3Adapter
from phantom_backend.games.eldenring.adapter import EldenRingAdapter


class GameRegistry:
    def __init__(self):
        self._adapters: dict[str, GameAdapter] = {
            "eldenring": EldenRingAdapter(),
            "ds3": Ds3Adapter(),
        }

    def get(self, key: str) -> GameAdapter:
        if key not in self._adapters:
            raise KeyError(f"Unknown game: {key}")
        return self._adapters[key]

    def list_games(self) -> list[str]:
        return sorted(self._adapters.keys())
