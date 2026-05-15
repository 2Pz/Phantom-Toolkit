"""Backup API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from phantom_backend.services import backup_service

router = APIRouter(prefix="/backup", tags=["backup"])


# ---- Models ----


class BackupSettingsModel(BaseModel):
    game: str = ""
    save_directory: str = ""
    backup_directory: str = ""
    save_file_type: str = ".sl2"
    save_file_name: str = ""
    backup_method: int = 0
    auto_backup_interval: int = 5
    sleep_between_saves: int = 10
    max_backups: int = 20
    quit_to_menu_before_load: bool = False
    notification_volume: int = 50
    keybind_save: str = ""
    keybind_load: str = ""
    keybind_auto_start: str = ""
    keybind_auto_stop: str = ""


class RenameModel(BaseModel):
    game: str = ""
    old_name: str
    new_name: str


class PinModel(BaseModel):
    game: str = ""
    pin: bool


class CreateBackupModel(BaseModel):
    game: str = ""
    request_save: bool = True


class AutoStartModel(BaseModel):
    game: str = ""


# ---- Endpoints ----


@router.get("/settings")
def get_settings(game: str = ""):
    settings = backup_service.load_settings(game_key=game)
    # Ensure hotkeys are initialized for this game context
    backup_service.initialize_hotkeys(game_key=game)
    return settings


@router.post("/initialize")
def initialize_backup(game: str = ""):
    backup_service.initialize_hotkeys(game_key=game)
    return {"ok": True}


@router.post("/settings")
def post_settings(body: BackupSettingsModel):
    settings = body.model_dump(exclude={"game"})
    backup_service.save_settings(settings, game_key=body.game)
    return {"ok": True}


@router.get("/auto-find")
def auto_find(game: str = ""):
    paths = backup_service._default_save_paths(game_key=game)
    return {"paths": paths}


@router.get("/save-files")
def list_save_files(save_dir: str, ext: str = ".sl2"):
    """List save files in a directory matching the given extension."""
    files = backup_service.list_save_files(save_dir, ext)
    return {"files": files}


@router.get("/list")
def list_all(game: str = ""):
    return backup_service.list_backups(game_key=game)


@router.post("/create")
def create(body: CreateBackupModel):
    # Safety Check
    if body.game:
        st = backup_service._check_game_status(body.game)
        if not st["attached"]:
            raise HTTPException(status_code=400, detail="Game not attached")

    # Optionally request save from the game first
    if body.request_save and body.game:
        try:
            from phantom_backend.games.registry import GameRegistry
            from phantom_backend.services.actions import ActionsService

            reg = GameRegistry()
            adapter = reg.get(body.game)
            mem = adapter.make_memory()
            try:
                resolver = adapter.make_resolver(mem)
                ActionsService(
                    mem=mem, resolver=resolver, game_key=body.game
                ).request_save()
            finally:
                mem.close()
            # Wait a moment for the save to complete
            import time

            time.sleep(2)
        except Exception:
            # Game might not be running, still do the backup
            pass

    try:
        result = backup_service.create_backup(game_key=body.game)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/load")
def load(name: str, game: str = ""):
    # Safety Check
    if game:
        st = backup_service._check_game_status(game)
        if not st["attached"]:
            raise HTTPException(status_code=400, detail="Game not attached")

    try:
        result = backup_service.load_backup(name, game_key=game)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{name}")
def delete(name: str, game: str = ""):
    try:
        return backup_service.delete_backup(name, game_key=game)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/pin/{name}")
def pin(name: str, body: PinModel):
    try:
        return backup_service.pin_backup(name, body.pin, game_key=body.game)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/rename")
def rename(body: RenameModel):
    try:
        return backup_service.rename_backup(
            body.old_name, body.new_name, game_key=body.game
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/screenshot/{name}")
def screenshot(name: str, game: str = ""):
    """Return screenshot PNG from a backup zip."""
    data = backup_service.get_screenshot(name, game_key=game)
    if data is None:
        raise HTTPException(status_code=404, detail="No screenshot found")
    return Response(content=data, media_type="image/png")


@router.post("/auto/start")
def auto_start(body: AutoStartModel):
    return backup_service.start_auto_backup(game_key=body.game)


@router.post("/auto/stop")
def auto_stop():
    return backup_service.stop_auto_backup()


@router.get("/auto/status")
def auto_status():
    return backup_service.is_auto_backup_running()
