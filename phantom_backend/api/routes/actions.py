from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends

from phantom_backend.games.registry import GameRegistry
from phantom_backend.services.actions import ActionsService

router = APIRouter(prefix="/{game}/actions", tags=["actions"])


def get_actions_service(game: str) -> Generator[ActionsService, None, None]:
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        yield ActionsService(mem=mem, resolver=resolver, game_key=game)
    finally:
        mem.close()


@router.post("/quit_to_menu")
def quit_to_menu(service: ActionsService = Depends(get_actions_service)):
    service.quit_to_menu()
    return {"ok": True}


@router.post("/fogwall")
def fogwall(
    animation_id: int = 60060, service: ActionsService = Depends(get_actions_service)
):
    service.fogwall_anim(animation_id)
    return {"ok": True}


@router.post("/request_save")
def request_save(service: ActionsService = Depends(get_actions_service)):
    service.request_save()
    return {"ok": True}


@router.post("/loading_fix/start")
def loading_fix_start(service: ActionsService = Depends(get_actions_service)):
    service.loading_fix_start()
    return {"ok": True}


@router.post("/loading_fix/stop")
def loading_fix_stop(service: ActionsService = Depends(get_actions_service)):
    service.loading_fix_stop()
    return {"ok": True}
