from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from phantom_backend.services.item_catalog import lookup as catalog_lookup
from phantom_backend.services.items import ItemAssetService, group_weapon_variants

router = APIRouter(prefix="/{game}", tags=["items"])


@router.get("/items/csvs")
def list_csvs(game: str):
    svc = ItemAssetService(game_key=game)
    return {"csvs": svc.list_csv_files()}


@router.get("/items/slot-categories")
def get_slot_categories(game: str, slot: str):
    svc = ItemAssetService(game_key=game)
    resolved = catalog_lookup(game, slot)
    if not resolved:
        return {"categories": []}
    csv_name, cat_col, allowed_cats = resolved
    if allowed_cats is None:
        if csv_name == "EquipParamWeapon.csv":
            cats = svc.get_distinct_weapon_categories()
        else:
            cats = list(svc.get_distinct_categories(csv_name, cat_col))
    else:
        cats = allowed_cats
    return {"categories": cats}


@router.get("/items/search")
def search_items(  # noqa: PLR0913
    game: str,
    q: str,
    csv: str | None = None,
    slot: str | None = None,
    category: list[str] = Query(None),
    lang: str | None = None,
    limit: int = 50,
):
    svc = ItemAssetService(game_key=game)

    if slot:
        resolved = catalog_lookup(game, slot)
        if resolved:
            csv_name, _cat_col, allowed_cats = resolved
            csv = csv_name
            if not category:
                if allowed_cats is None and csv_name == "EquipParamWeapon.csv":
                    category = svc.get_distinct_weapon_categories()
                elif allowed_cats is not None:
                    category = allowed_cats

    # For weapons, request more raw items so variant grouping yields meaningful results.
    # Each base weapon can have ~13 affinity rows, so multiply the limit to account for them.
    internal_limit = max(limit, limit * 20) if csv == "EquipParamWeapon.csv" else limit
    hits = svc.search_items(
        csv_name=csv, q=q, categories=category, language=lang, limit=internal_limit
    )
    items = [h.__dict__ for h in hits]
    if csv == "EquipParamWeapon.csv":
        items = group_weapon_variants(items)
    return {"items": items[:limit]}


@router.get("/items/get")
def get_item(game: str, csv: str, id: int, lang: str | None = None):
    svc = ItemAssetService(game_key=game)
    item = svc.get_item(csv_name=csv, item_id=id, language=lang)
    return {"item": item.__dict__}


@router.get("/items/enrich-weapon")
def enrich_weapon(game: str, id: int, lang: str | None = None):
    """Given any weapon variant ID, return the grouped entry with all variants/baseId/baseName."""
    svc = ItemAssetService(game_key=game)
    item = svc.enrich_weapon(id, lang)
    return {"item": item}


@router.get("/icons/{icon_id}")
def get_icon(game: str, icon_id: str):
    svc = ItemAssetService(game_key=game)
    data, fmt = svc.read_icon_data(icon_id)

    media_type = "application/octet-stream"
    if fmt == "webp":
        media_type = "image/webp"
    elif fmt == "png":
        media_type = "image/png"
    elif fmt == "dds":
        media_type = "image/vnd.ms-dds"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000"},
    )


class InspectBuildRequest(BaseModel):
    equipment: dict[str, Any]  # dict of slot -> id (int) or {id: int}


def _csv_hints_for_slot(game: str, slot_key: str) -> list[str] | None:
    """Resolve slot key to CSV hints via the catalog."""
    resolved = catalog_lookup(game, slot_key)
    if resolved is None:
        return None
    csv_name, _cat_col, _cats = resolved
    return [csv_name]


@router.post("/items/inspect_build")
def inspect_build(game: str, req: InspectBuildRequest):
    """
    Enrich a raw equipment dictionary (IDs) with item details (Name, Icon, MaxUpgrade).
    Used for loading external build files.
    """
    svc = ItemAssetService(game_key=game)
    enriched = {}

    for slot, val in req.equipment.items():
        item_id = -1
        ash_of_war_id = -1

        if isinstance(val, int):
            item_id = val
        elif isinstance(val, dict):
            item_id = val.get("id", -1)
            ash_of_war_id = val.get("ash_of_war", -1)

        if item_id in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
            enriched[slot] = None
            continue

        if item_id > -1:
            hints = _csv_hints_for_slot(game, slot)

            found = svc.find_item_any_csv(item_id, hints=hints)
            if found:
                enriched[slot] = {
                    "id": item_id,
                    "name": found.name,
                    "icon_id": found.icon_id,
                    "max_upgrade": found.max_upgrade,
                    "category": found.category,
                }

                if ash_of_war_id > -1:
                    gem_hints = _csv_hints_for_slot(game, "gem") or [
                        "EquipParamGem.csv"
                    ]
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
