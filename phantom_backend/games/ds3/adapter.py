from __future__ import annotations

from pathlib import Path

from phantom_backend.games.base import BaseGameAdapter


class Ds3Adapter(BaseGameAdapter):
    def __init__(self):
        super().__init__(
            key="ds3",
            process_name="DarkSoulsIII.exe",
            module_name="DarkSoulsIII.exe",
            signatures_toml=Path(__file__).with_name("signatures.toml"),
        )

    def required_symbols(self) -> list[str]:
        return [
            "WorldChrManPtrAddr",
            "GameDataManPtrAddr",
            "GameManPtrAddr",
            "SaveRequestThreadStart",
            # Build/equip
            "EquipGearFunc",
            "EquipGoodsFunc",
            "ItemGiveFunc",
        ]
