from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

from fastapi import APIRouter

from phantom_backend.config_manager import ConfigManager
from phantom_backend.games.registry import GameRegistry
from phantom_backend.utils.platform_utils import browse_directory as open_browse_dialog
from phantom_backend.utils.platform_utils import save_file_dialog

router = APIRouter(prefix="/system", tags=["system"])

_IS_APPIMAGE = os.environ.get("PHANTOM_LAUNCHED_BY_APPIMAGE") == "1"
_LINUX_HOME = os.environ.get("PHANTOM_LINUX_HOME", "")
_HOST_BRIDGE_URL = os.environ.get("PHANTOM_HOST_BRIDGE_URL", "").rstrip("/")


def _linux_to_wine(path: str) -> str:
    """Convert a Linux absolute path to Wine Z: drive path for os access."""
    return "Z:" + path.replace("/", "\\")


def _host_bridge_get_json(endpoint: str, params: dict[str, str] | None = None) -> dict:
    if not _HOST_BRIDGE_URL:
        raise RuntimeError("PHANTOM_HOST_BRIDGE_URL not set")
    base = f"{_HOST_BRIDGE_URL}{endpoint}"
    if params:
        q = urllib.parse.urlencode(params)
        url = f"{base}?{q}"
    else:
        url = base
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        raw = resp.read()
    # The bridge returns JSON for most endpoints.
    import json

    return json.loads(raw.decode("utf-8"))


@router.get("/list_dirs")
def list_dirs(path: str = "") -> dict:
    """List subdirectories at *path* so the frontend can browse.

    Under AppImage/Proton the Wine process uses the Z: drive to reach real
    Linux paths.  The API always speaks Linux-style paths to the frontend
    and translates internally.
    """
    # Default starting directory
    if not path:
        path = _LINUX_HOME if _LINUX_HOME else os.path.expanduser("~")

    # Normalise (remove trailing slash except root)
    path = path.rstrip("/") or "/"

    # Under Wine, translate so os.listdir works on the real filesystem
    access_path = _linux_to_wine(path) if _IS_APPIMAGE else path

    dirs: list[str] = []
    try:
        for entry in sorted(os.listdir(access_path)):
            if entry.startswith("."):
                continue
            full = os.path.join(access_path, entry)
            if os.path.isdir(full):
                dirs.append(entry)
    except PermissionError:
        pass
    except FileNotFoundError:
        pass

    parent = str(PurePosixPath(path).parent) if path != "/" else None
    return {"path": path, "dirs": dirs, "parent": parent}


@router.get("/detected_game")
def detected_game() -> dict[str, str | None]:
    """Detect which supported game is currently running."""
    reg = GameRegistry()
    for game_key in reg.list_games():
        adapter = reg.get(game_key)
        try:
            # excessive wait=False to just check existence quickly
            mem = adapter.make_memory()
            mem.close()
            return {"game": game_key}
        except Exception:
            # If make_memory fails (process not found), continue to next
            continue

    return {"game": None}


@router.get("/browse_directory")
def browse_directory(initial_dir: str = "") -> dict[str, str | None]:
    """Open a system folder picker and return the path."""
    if _IS_APPIMAGE and _HOST_BRIDGE_URL:
        try:
            data = _host_bridge_get_json(
                "/browse_directory", {"initial_dir": initial_dir}
            )
            return {"path": data.get("path")}
        except urllib.error.HTTPError as e:
            # If a dialog is already open, don't fall back (that would pop another dialog).
            if getattr(e, "code", None) == 409:
                return {"path": None}
        except Exception:
            # If the bridge is misconfigured/unreachable, don't silently no-op.
            # Fall back to the best-available dialog in this environment.
            pass

    path = open_browse_dialog(initial_dir)
    return {"path": path}


@router.get("/browse_save_file")
def browse_save_file(default_name: str = "build") -> dict[str, str | None]:
    """Open a system save file dialog and return the path."""
    cm = ConfigManager()
    initial_dir = cm.last_save_dir

    if _IS_APPIMAGE and _HOST_BRIDGE_URL:
        try:
            data = _host_bridge_get_json(
                "/save_file", {"initial_dir": initial_dir, "default_name": default_name}
            )
            path = data.get("path")
            if path:
                cm.last_save_dir = os.path.dirname(path)
            return {"path": path}
        except urllib.error.HTTPError as e:
            if getattr(e, "code", None) == 409:
                return {"path": None}
        except Exception:
            # Bridge failed; fall back to local dialog implementation.
            pass

    path = save_file_dialog(initial_dir, default_name)

    if path:
        # Update last save dir
        cm.last_save_dir = os.path.dirname(path)

    return {"path": path}


@router.get("/host_bridge_status")
def host_bridge_status() -> dict[str, object]:
    """Debug endpoint: confirms whether AppImage host bridge is configured/reachable."""
    out: dict[str, object] = {
        "is_appimage": _IS_APPIMAGE,
        "host_bridge_url": _HOST_BRIDGE_URL or None,
        "linux_home": _LINUX_HOME or None,
    }
    if not _HOST_BRIDGE_URL:
        out["reachable"] = False
        return out
    # Do a simple raw ping.
    try:
        req = urllib.request.Request(f"{_HOST_BRIDGE_URL}/ping", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
            out["reachable"] = getattr(resp, "status", 200) == 200
    except Exception:
        out["reachable"] = False
        return out

    # Also expose /status if available (capture method + tool availability).
    try:
        data = _host_bridge_get_json("/status", None)
        out["bridge_status"] = data
    except Exception:
        out["bridge_status"] = None
    return out


@router.get("/config")
def get_config() -> dict[str, object]:
    """Get current configuration."""
    cm = ConfigManager()
    return {
        "language": cm.language,
        # Add other config fields here as needed
    }


@router.post("/config")
def update_config(config: dict[str, object]) -> dict[str, object]:
    """Update configuration."""
    cm = ConfigManager()
    if "language" in config:
        cm.language = str(config["language"])
    return {
        "language": cm.language,
    }
