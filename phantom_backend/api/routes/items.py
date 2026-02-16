from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from phantom_backend.services.items import ItemAssetService

router = APIRouter(prefix="/{game}", tags=["items"])


@router.get("/items/csvs")
def list_csvs(game: str):
    svc = ItemAssetService(game_key=game)
    return {"csvs": svc.list_csv_files()}


@router.get("/items/search")
def search_items(
    game: str, q: str, csv: str | None = None, lang: str = "en", limit: int = 50
):
    svc = ItemAssetService(game_key=game)
    hits = svc.search_items(csv_name=csv, q=q, language=lang, limit=limit)
    return {"items": [h.__dict__ for h in hits]}


@router.get("/items/get")
def get_item(game: str, csv: str, id: int, lang: str = "en"):
    svc = ItemAssetService(game_key=game)
    item = svc.get_item(csv_name=csv, item_id=id, language=lang)
    return {"item": item.__dict__}


@router.get("/icons/{icon_id}")
def get_icon(game: str, icon_id: str):
    svc = ItemAssetService(game_key=game)
    data = svc.read_icon_png(icon_id)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000"},
    )


class InspectBuildRequest(BaseModel):
    equipment: dict[str, Any]  # dict of slot -> id (int) or {id: int}


SLOT_CSV_MAP = {
    "helmet": ["Heads.csv"],
    "armor": ["Chests.csv"],
    "gauntlet": ["Gauntlets.csv"],
    "leggings": ["Leggings.csv"],
    "accessory": ["Talismans.csv", "Rings.csv"],
    "talisman": ["Talismans.csv"],
    "ring": ["Rings.csv", "Talismans.csv", "Accessories.csv"],
    "weapon": ["Weapons.csv"],
    "wep": ["Weapons.csv"],
    "arrow": ["Ammunitions.csv"],
    "bolt": ["Ammunitions.csv"],
    "magic": ["Spells.csv"],
    "spell": ["Spells.csv"],
    "quick": ["QuickItems.csv"],
}


@router.post("/items/inspect_build")
def inspect_build(game: str, req: InspectBuildRequest):
    """
    Enrich a raw equipment dictionary (IDs) with item details (Name, Icon, MaxUpgrade).
    Used for loading external build files.
    """
    svc = ItemAssetService(game_key=game)
    enriched = {}

    for slot, val in req.equipment.items():
        # Handle simple int ID or dict with "id"
        item_id = -1
        ash_of_war_id = -1

        if isinstance(val, int):
            item_id = val
        elif isinstance(val, dict):
            item_id = val.get("id", -1)
            ash_of_war_id = val.get("ash_of_war", -1)

        # Treat sentinel IDs as empty slots (common in saved builds).
        # 0x0FFFFFFF is frequently used as a placeholder "empty" item id in ER/DS3 tooling.
        if item_id in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
            enriched[slot] = None
            continue

        if item_id > -1:
            # Determine hints
            hints = []
            for k, v in SLOT_CSV_MAP.items():
                if k in slot:
                    hints.extend(v)
                    break

            found = svc.find_item_any_csv(item_id, hints=hints)
            if found:
                enriched[slot] = {
                    "id": item_id,  # Return ORIGINAL ID
                    "name": found.name,
                    "icon_id": found.icon_id,
                    "max_upgrade": found.max_upgrade,
                }

                if ash_of_war_id > -1:
                    # Gems hinted?
                    gem_hints = ["Gems.csv", "AshOfWarsIDs.csv"]
                    gem_found = svc.find_item_any_csv(ash_of_war_id, hints=gem_hints)
                    if gem_found:
                        enriched[slot]["gem_name"] = gem_found.name
                        enriched[slot]["gem_icon"] = gem_found.icon_id
                        enriched[slot]["gem_id"] = ash_of_war_id
            else:
                enriched[slot] = {"id": item_id, "name": f"Unknown [{item_id}]"}
        else:
            enriched[slot] = None

    return {"equipment": enriched}
