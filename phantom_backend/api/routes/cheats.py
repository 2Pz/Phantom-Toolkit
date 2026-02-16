from __future__ import annotations

from fastapi import APIRouter

from phantom_backend.games.registry import GameRegistry
from phantom_backend.services.cheats import CheatsService

router = APIRouter(prefix="/{game}", tags=["cheats"])


@router.get("/cheats")
def list_cheats(game: str):
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        svc = CheatsService(mem=mem, resolver=resolver, game_key=game)
        return {"cheats": [c.__dict__ for c in svc.list_cheats()]}
    finally:
        mem.close()


@router.post("/cheats/{cheat_name}/{action}")
def set_cheat(game: str, cheat_name: str, action: str):
    enable = action.lower() == "enable"
    if action.lower() not in {"enable", "disable"}:
        return {"ok": False, "error": "action must be enable|disable"}

    try:
        reg = GameRegistry()
        adapter = reg.get(game)
        mem = adapter.make_memory()
        try:
            resolver = adapter.make_resolver(mem)
            svc = CheatsService(mem=mem, resolver=resolver, game_key=game)
            svc.set_cheat(cheat_name, enable)
            return {"ok": True}
        finally:
            mem.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}
