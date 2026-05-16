from __future__ import annotations

from fastapi import APIRouter

from phantom_backend.api.models import (
    PlayerDetails,
    WriteBuildRequest,
    WriteStatsRequest,
)
from phantom_backend.games.registry import GameRegistry
from phantom_backend.services.item_catalog import lookup as catalog_lookup
from phantom_backend.services.items import ItemAssetService
from phantom_backend.services.players import PlayerService
from phantom_backend.services.recent_players import RecentPlayersService

router = APIRouter(prefix="/{game}", tags=["players"])


def _csv_hints_for_slot(game: str, slot_key: str) -> list[str] | None:
    resolved = catalog_lookup(game, slot_key)
    if resolved is None:
        return None
    csv_name, _cat_col, _cats = resolved
    return [csv_name]


def _enrich_player_data(p: PlayerService.PlayerState, game: str) -> PlayerDetails:
    item_svc = ItemAssetService(game_key=game)
    enriched_eq = {}
    if p.equipment:
        for slot, item_val in p.equipment.items():
            if item_val in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
                enriched_eq[slot] = None
                continue

            if isinstance(item_val, int) and item_val > -1:
                hints = _csv_hints_for_slot(game, slot)
                found = item_svc.find_item_any_csv(item_val, hints=hints)
                if found:
                    enriched_eq[slot] = {
                        "id": item_val,
                        "name": found.name,
                        "icon_id": found.icon_id,
                        "max_upgrade": found.max_upgrade,
                    }
                else:
                    enriched_eq[slot] = {
                        "id": item_val,
                        "name": f"Unknown [{item_val}]",
                    }
            else:
                enriched_eq[slot] = None

    stats = p.stats or {}
    if p.steam_id:
        stats["steamId"] = p.steam_id

    return PlayerDetails(
        player_num=p.player_num,
        is_valid=p.is_valid,
        name=p.name,
        level=p.level,
        stats=stats,
        equipment=enriched_eq,
    )


@router.get("/players/recent", response_model=list[PlayerDetails])
def list_recent_players(game: str):
    svc = RecentPlayersService(game_key=game)
    return svc.get_recent_players()


@router.get("/players", response_model=list[PlayerDetails])
def list_players(game: str):
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        svc = PlayerService(mem=mem, resolver=resolver, game_key=game)
        players = svc.list_players()
        enriched = [_enrich_player_data(p, game) for p in players]

        # Save to recent players
        recent_svc = RecentPlayersService(game_key=game)
        recent_svc.add_players(enriched)

        return enriched
    finally:
        mem.close()


@router.get("/players/{player_num}", response_model=PlayerDetails)
def get_player(game: str, player_num: int):
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        svc = PlayerService(mem=mem, resolver=resolver, game_key=game)
        p = svc.get_player(player_num)
        return _enrich_player_data(p, game)
    finally:
        mem.close()


@router.post("/players/{player_num}/stats")
def write_stats(game: str, player_num: int, req: WriteStatsRequest):
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        svc = PlayerService(mem=mem, resolver=resolver, game_key=game)
        svc.write_stats(player_num, req.stats)
        return {"ok": True}
    finally:
        mem.close()


@router.post("/players/{player_num}/build")
def write_build(game: str, player_num: int, req: WriteBuildRequest):
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        svc = PlayerService(mem=mem, resolver=resolver, game_key=game)

        # stats may be provided alongside equipment in common build JSON formats
        if req.stats:
            combined = dict(req.stats)
            if req.shadow_of_erdtree:
                combined["shadow_of_erdtree"] = req.shadow_of_erdtree
            svc.write_stats(player_num, combined)

        svc.write_build(player_num, req.equipment)

        # Return the updated player state so the UI stays in sync (showing Naked IDs, etc.)
        p = svc.get_player(player_num)
        return _enrich_player_data(p, game)
    finally:
        mem.close()
