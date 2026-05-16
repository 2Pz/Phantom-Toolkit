from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phantom_backend.services.items import ItemAssetService

SENTINEL_IDS = frozenset((-1, 0xFFFFFFFF, 0x0FFFFFFF))

# Maps backend slot key -> (csv_filename, category_column, list_of_allowed_category_values | None)
# None for categories means all items in that CSV are valid for this slot.
SLOT_DEFINITIONS: dict[str, dict[str, tuple[str, str, list[str] | None]]] = {
    "eldenring": {
        "helmet": ("EquipParamProtector.csv", "category", ["Head"]),
        "armor": ("EquipParamProtector.csv", "category", ["Body"]),
        "gauntlet": ("EquipParamProtector.csv", "category", ["Arms"]),
        "leggings": ("EquipParamProtector.csv", "category", ["Legs"]),
        "accessory": ("EquipParamAccessory.csv", "category", ["Accessory"]),
        "talisman": ("EquipParamAccessory.csv", "category", ["Accessory"]),
        "ring": ("EquipParamAccessory.csv", "category", ["Accessory"]),
        "covenant": ("EquipParamAccessory.csv", "category", ["Accessory"]),
        "weapon": ("EquipParamWeapon.csv", "category", None),
        "wep": ("EquipParamWeapon.csv", "category", None),
        "arrow": ("EquipParamWeapon.csv", "category", ["arrow"]),
        "bolt": ("EquipParamWeapon.csv", "category", ["bolt"]),
        "spell": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Spell",
                "Sorcery",
                "Incantation",
                "Self Buff - Sorcery",
                "Self Buff - Incantation",
            ],
        ),
        "magic": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Spell",
                "Sorcery",
                "Incantation",
                "Self Buff - Sorcery",
                "Self Buff - Incantation",
            ],
        ),
        "quick": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Normal Item",
                "Key Item",
                "Consumable",
                "Crafting Material",
                "Regenerative Material",
                "Reinforcement Material",
                "Info Item",
                "None",
                "Remembrance",
                "Great Rune",
                "Spirit Summon - Lesser",
                "Spirit Summon - Greater",
            ],
        ),
        "quick_item": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Normal Item",
                "Key Item",
                "Consumable",
                "Crafting Material",
                "Regenerative Material",
                "Reinforcement Material",
                "Info Item",
                "None",
                "Remembrance",
                "Great Rune",
                "Spirit Summon - Lesser",
                "Spirit Summon - Greater",
            ],
        ),
        "physick": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Wondrous Physick",
                "Wondrous Physick Tear",
            ],
        ),
        "gem": ("EquipParamGem.csv", "category", None),
        "ash_of_war": ("EquipParamGem.csv", "category", None),
    },
    "ds3": {
        "helmet": ("EquipParamProtector.csv", "category", ["Head"]),
        "armor": ("EquipParamProtector.csv", "category", ["Body"]),
        "gauntlet": ("EquipParamProtector.csv", "category", ["Hands"]),
        "leggings": ("EquipParamProtector.csv", "category", ["Legs"]),
        "accessory": ("EquipParamAccessory.csv", "category", ["Ring", "Covenant"]),
        "ring": ("EquipParamAccessory.csv", "category", ["Ring"]),
        "talisman": ("EquipParamAccessory.csv", "category", ["Ring"]),
        "covenant": ("EquipParamAccessory.csv", "category", ["Covenant"]),
        "weapon": ("EquipParamWeapon.csv", "category", None),
        "wep": ("EquipParamWeapon.csv", "category", None),
        "arrow": ("EquipParamWeapon.csv", "category", ["arrow"]),
        "bolt": ("EquipParamWeapon.csv", "category", ["bolt"]),
        "spell": ("EquipParamGoods.csv", "goods_type", ["Spell"]),
        "magic": ("EquipParamGoods.csv", "goods_type", ["Spell"]),
        "quick": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Consumable",
                "Key Item",
                "Material",
            ],
        ),
        "quick_item": (
            "EquipParamGoods.csv",
            "goods_type",
            [
                "Consumable",
                "Key Item",
                "Material",
            ],
        ),
    },
}


def lookup(game_key: str, slot_key: str) -> tuple[str, str, list[str] | None] | None:
    """Resolve a slot key to (csv_name, category_column, allowed_categories).

    Returns None if the game or slot key is unknown.
    """
    game_defs = SLOT_DEFINITIONS.get(game_key)
    if game_defs is None:
        return None

    if slot_key in game_defs:
        return game_defs[slot_key]

    # Substring fallback: longest match wins
    candidates = [(len(k), k, v) for k, v in game_defs.items() if k in slot_key]
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][2]

    return None


def csv_hints_for_slot(game_key: str, slot_key: str) -> list[str] | None:
    """Resolve slot key to list of CSV filenames (for find_item_any_csv)."""
    resolved = lookup(game_key, slot_key)
    if resolved is None:
        return None
    return [resolved[0]]


def enrich_equipment_slot(
    game_key: str,
    slot_key: str,
    item_id: int,
    item_svc: ItemAssetService,
) -> dict | None:
    """Look up an item ID for a given slot and return enriched metadata.

    Returns None for sentinel/empty IDs, or a dict with id/name/icon_id/max_upgrade.
    """
    if item_id in SENTINEL_IDS:
        return None

    hints = csv_hints_for_slot(game_key, slot_key)
    found = item_svc.find_item_any_csv(item_id, hints=hints)
    if found:
        return {
            "id": item_id,
            "name": found.name,
            "icon_id": found.icon_id,
            "max_upgrade": found.max_upgrade,
        }
    return {"id": item_id, "name": f"Unknown [{item_id}]"}


def csv_names_for_game(game_key: str) -> set[str]:
    """Return all distinct CSV filenames referenced for a game."""
    names: set[str] = set()
    for csv_name, _cat_col, _cats in SLOT_DEFINITIONS.get(game_key, {}).values():
        names.add(csv_name)
    return names
