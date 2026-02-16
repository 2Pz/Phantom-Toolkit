from __future__ import annotations

from pathlib import Path

from phantom_backend.games.base import BaseGameAdapter


class EldenRingAdapter(BaseGameAdapter):
    def __init__(self):
        super().__init__(
            key="eldenring",
            process_name="eldenring.exe",
            module_name="eldenring.exe",
            signatures_toml=Path(__file__).with_name("signatures.toml"),
        )

    def required_symbols(self) -> list[str]:
        # AOB-only: these must be provided in signatures.toml for runtime features.
        return [
            "WorldChrManPtrAddr",
            "GameDataManPtrAddr",
            "GameManPtrAddr",
        ]
