"""Save backup service — cross-platform (Windows + Linux)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import platform
import posixpath
import subprocess
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from phantom_backend.config_manager import ConfigManager

try:
    import keyboard
except ImportError:
    keyboard = None

# ---------------------------------------------------------------------------
# Platform-specific screenshot helpers
# ---------------------------------------------------------------------------


def _is_appimage_proton_backend() -> bool:
    """True when the backend is running under Proton/Wine via the AppImage wrapper."""
    return (
        os.environ.get("PHANTOM_LAUNCHED_BY_APPIMAGE", "0") == "1"
        and platform.system() == "Windows"
    )


def _linux_to_wine_z_path(path: str) -> str:
    """Convert /home/user/foo -> Z:\\home\\user\\foo (for Wine filesystem access)."""
    if not path or not path.startswith("/"):
        return path
    return "Z:" + path.replace("/", "\\")


def _access_path(path: str) -> str:
    """Translate POSIX paths to Wine Z: paths when needed for filesystem access."""
    if _is_appimage_proton_backend() and path.startswith("/"):
        return _linux_to_wine_z_path(path)
    return path


def _get_game_window_titles() -> list[str]:
    """Return known game window titles to search for."""
    return [
        "ELDEN RING™",
        "ELDEN RING",
        "DARK SOULS III",
        "DARK SOULS™ III",
    ]


def _capture_screenshot_win() -> bytes | None:
    """Capture active game window screenshot on Windows using mss + win32gui."""
    try:
        import ctypes

        import mss

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        # Try to find game window
        target_hwnd = None
        titles = _get_game_window_titles()

        def _enum_callback(hwnd: int, _: Any) -> bool:
            nonlocal target_hwnd
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                for t in titles:
                    if t.lower() in title.lower():
                        target_hwnd = hwnd
                        return False  # stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
        )
        enum_func = WNDENUMPROC(_enum_callback)
        user32.EnumWindows(enum_func, 0)

        if target_hwnd is None:
            return None

        # Get window rect
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        user32.GetClientRect(target_hwnd, ctypes.byref(rect))

        # Convert client to screen coordinates
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT(0, 0)
        user32.ClientToScreen(target_hwnd, ctypes.byref(pt))

        monitor = {
            "left": pt.x,
            "top": pt.y,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }

        if monitor["width"] <= 0 or monitor["height"] <= 0:
            return None

        with mss.mss() as sct:
            img = sct.grab(monitor)
            # Convert to PNG bytes
            from PIL import Image

            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            # Resize for better quality (max 1920 wide)
            w, h = pil_img.size
            if w > 1920:
                ratio = 1920 / w
                pil_img = pil_img.resize((1920, int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


def _get_linux_primary_monitor_geometry() -> tuple[int, int, int, int] | None:
    """Detect primary monitor geometry (x, y, width, height) on Linux."""
    # 1. Try kscreen-doctor (KDE)
    try:
        result = subprocess.run(
            ["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            # Find which output has priority 1
            for i, line in enumerate(lines):
                if "priority 1" in line:
                    # Look for Geometry in nearby lines (usually the next line)
                    for j in range(max(0, i - 5), min(len(lines), i + 5)):
                        if "Geometry:" in lines[j]:
                            # Format: "Geometry: 1920,0 2560x1440"
                            parts = lines[j].split("Geometry:")[1].strip().split()
                            pos_parts = parts[0].split(",")
                            size_parts = parts[1].split("x")
                            return (
                                int(pos_parts[0]),
                                int(pos_parts[1]),
                                int(size_parts[0]),
                                int(size_parts[1]),
                            )
    except Exception:
        pass

    # 2. Fallback to mss for monitor metadata (X11/metadata-only)
    try:
        import mss

        with mss.mss() as sct:
            if len(sct.monitors) > 1:
                m = sct.monitors[1]
                return m["left"], m["top"], m["width"], m["height"]
    except Exception:
        pass

    return None


def _capture_screenshot_linux() -> bytes | None:
    """Capture full desktop and crop to primary monitor on Linux."""
    from PIL import Image

    geom = _get_linux_primary_monitor_geometry()

    def try_cmd(cmd: list[str], output_file: str) -> bytes | None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)
            if os.path.exists(output_file):
                img = Image.open(output_file)
                # Crop to primary monitor if detected
                if geom:
                    x, y, w, h = geom
                    # Image.crop uses (left, top, right, bottom)
                    # Coordinates might be negative in some setups, but usually (0,0) is origin
                    # We need to make sure coordinates are within image bounds
                    img_w, img_h = img.size
                    left = max(0, min(x, img_w))
                    top = max(0, min(y, img_h))
                    right = max(left, min(x + w, img_w))
                    bottom = max(top, min(y + h, img_h))
                    if right > left and bottom > top:
                        img = img.crop((left, top, right, bottom))

                # Resize for consistency/performance
                iw, ih = img.size
                if iw > 1280:
                    ratio = 1280 / iw
                    img = img.resize((1280, int(ih * ratio)), Image.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="PNG")
                data = buf.getvalue()
                os.remove(output_file)
                return data
        except Exception:
            if os.path.exists(output_file):
                os.remove(output_file)
        return None

    tmp_ss = "/tmp/phantom_ss.png"

    # 1. Try spectacle (KDE/Wayland/X11) - Full Screen
    data = try_cmd(["spectacle", "-f", "-b", "-n", "-o", tmp_ss], tmp_ss)
    if data:
        return data

    # 2. Try gnome-screenshot (GNOME/X11) - Full Screen
    data = try_cmd(["gnome-screenshot", "-f", tmp_ss], tmp_ss)
    if data:
        return data

    # 3. Try grim (Generic Wayland) - Full Screen
    data = try_cmd(["grim", tmp_ss], tmp_ss)
    if data:
        return data

    # 4. Try scrot (Universal X11) - Full Screen
    data = try_cmd(["scrot", tmp_ss], tmp_ss)
    if data:
        return data

    # 5. Final fallback: mss full screen
    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[0]  # combined monitors
            # If we have geom, try to grab just that monitor's rect
            if geom:
                x, y, w, h = geom
                monitor = {"left": x, "top": y, "width": w, "height": h}

            img_data = sct.grab(monitor)
            pil_img = Image.frombytes(
                "RGB", img_data.size, img_data.bgra, "raw", "BGRX"
            )
            # Resize
            pw, ph = pil_img.size
            if pw > 1280:
                ratio = 1280 / pw
                pil_img = pil_img.resize((1280, int(ph * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass

    return None


def _capture_screenshot_via_host_bridge() -> bytes | None:
    """If running under AppImage, capture via native Linux helper."""
    base = os.environ.get("PHANTOM_HOST_BRIDGE_URL", "").strip().rstrip("/")
    if not base:
        return None
    url = f"{base}/screenshot"
    try:
        # Allow a short startup race window (bridge starts alongside the backend).
        for _ in range(10):
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                data = b"" if getattr(resp, "status", 200) != 200 else resp.read()
            # quick sanity check (PNG signature)
            if data and data[:8] == b"\x89PNG\r\n\x1a\n":
                return data
            time.sleep(0.35)
        return None
    except Exception:
        return None


def capture_screenshot() -> bytes | None:
    """Capture a screenshot of the game window. Returns PNG bytes or None."""
    # When running under the AppImage wrapper (Proton/Wine), do NOT fall back to the
    # Windows capture path (it often returns tiny black PNGs). Only use host bridge.
    if os.environ.get("PHANTOM_LAUNCHED_BY_APPIMAGE", "0") == "1":
        return _capture_screenshot_via_host_bridge()

    # In AppImage mode the backend runs inside Proton/Wine and capture often yields black frames.
    # Prefer native Linux capture via the host bridge when available.
    data = _capture_screenshot_via_host_bridge()
    if data:
        return data

    if platform.system() == "Windows":
        return _capture_screenshot_win()
    else:
        return _capture_screenshot_linux()


# ---------------------------------------------------------------------------
# Default save file paths
# ---------------------------------------------------------------------------


def _add_linux_steam_paths(paths: list[dict[str, str]], linux_home: str) -> None:
    """Search real Linux Steam paths for save files.

    Used when running under Proton — platform.system() returns "Windows"
    but the actual save files live on the Linux filesystem.
    """
    linux_home = (linux_home or "").strip()
    if not linux_home:
        return

    # Always construct *UI-facing* paths as POSIX, even under Wine.
    steam_candidates = [
        posixpath.join(linux_home, ".steam/steam/steamapps/compatdata"),
        posixpath.join(linux_home, ".local/share/Steam/steamapps/compatdata"),
        # Flatpak Steam
        posixpath.join(
            linux_home,
            ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata",
        ),
    ]

    er_appid = "1245620"
    ds3_appid = "374320"
    seen: set[str] = set()

    for steam_dir in steam_candidates:
        if not os.path.isdir(_access_path(steam_dir)):
            continue
        for appid, game in [(er_appid, "eldenring"), (ds3_appid, "ds3")]:
            base_posix = posixpath.join(
                steam_dir,
                appid,
                "pfx/drive_c/users/steamuser/AppData/Roaming",
                "EldenRing" if game == "eldenring" else "DarkSoulsIII",
            )
            base_access = _access_path(base_posix)
            if os.path.exists(base_access):
                for d in os.listdir(base_access):
                    full_posix = posixpath.join(base_posix, d)
                    full_access = _access_path(full_posix)
                    if os.path.isdir(full_access) and full_posix not in seen:
                        seen.add(full_posix)
                        paths.append({"path": full_posix, "game": game, "steam_id": d})


def _default_save_paths(game_key: str = "") -> list[dict[str, str]]:
    """Return common save file locations for auto-detection."""
    paths: list[dict[str, str]] = []
    system = platform.system()

    def _score_save_dir(p: str) -> tuple[int, int]:
        """(latest_mtime, file_count) for known save file types."""
        latest = 0
        count = 0
        p_access = _access_path(p or "")
        try:
            for fn in os.listdir(p_access):
                lower = fn.lower()
                if not lower.endswith((".sl2", ".co2")):
                    continue
                fp = os.path.join(p_access, fn)
                if not os.path.isfile(fp):
                    continue
                count += 1
                latest = max(latest, int(os.stat(fp).st_mtime))
        except Exception:
            return (0, 0)
        return (latest, count)

    def _pick_best(cands: list[dict[str, str]]) -> list[dict[str, str]]:
        if len(cands) <= 1:
            return cands
        best = max(cands, key=lambda d: _score_save_dir(d.get("path", "")))
        return [best]

    # When running under Proton (AppImage), also search real Linux Steam paths
    linux_home = os.environ.get("PHANTOM_LINUX_HOME", "")
    if linux_home:
        # Prefer the active game's compatdata prefix if available (more accurate than scanning).
        compatdata = os.environ.get("STEAM_COMPAT_DATA_PATH", "").strip()
        if compatdata and game_key in ("eldenring", "ds3"):
            roaming = "EldenRing" if game_key == "eldenring" else "DarkSoulsIII"
            base_posix = posixpath.join(
                compatdata,
                "pfx/drive_c/users/steamuser/AppData/Roaming",
                roaming,
            )
            base_access = _access_path(base_posix)
            if os.path.isdir(base_access):
                cands: list[dict[str, str]] = []
                for d in os.listdir(base_access):
                    full_posix = posixpath.join(base_posix, d)
                    if os.path.isdir(_access_path(full_posix)):
                        cands.append(
                            {"path": full_posix, "game": game_key, "steam_id": d}
                        )
                picked = _pick_best(cands)
                if picked:
                    return picked

        _add_linux_steam_paths(paths, linux_home)

    if system == "Windows":
        # Under Proton (AppImage), APPDATA points to Wine's virtual drive which
        # duplicates the real Linux Steam paths we already found above.
        # Skip it when we already have Linux results.
        if linux_home and paths:
            pass  # Linux paths already populated above
        elif appdata := os.environ.get("APPDATA", ""):
            er_base = os.path.join(appdata, "EldenRing")
            ds3_base = os.path.join(appdata, "DarkSoulsIII")
            if os.path.exists(er_base):
                for d in os.listdir(er_base):
                    full = os.path.join(er_base, d)
                    if os.path.isdir(full):
                        paths.append({"path": full, "game": "eldenring", "steam_id": d})
            if os.path.exists(ds3_base):
                for d in os.listdir(ds3_base):
                    full = os.path.join(ds3_base, d)
                    if os.path.isdir(full):
                        paths.append({"path": full, "game": "ds3", "steam_id": d})
    else:
        # Linux / Proton
        steam_dir = os.path.expanduser("~/.steam/steam/steamapps/compatdata")
        er_appid = "1245620"
        ds3_appid = "374320"
        for appid, game in [(er_appid, "eldenring"), (ds3_appid, "ds3")]:
            base = os.path.join(
                steam_dir,
                appid,
                "pfx/drive_c/users/steamuser/AppData/Roaming",
                "EldenRing" if game == "eldenring" else "DarkSoulsIII",
            )
            if os.path.exists(base):
                for d in os.listdir(base):
                    full = os.path.join(base, d)
                    if os.path.isdir(full):
                        paths.append({"path": full, "game": game, "steam_id": d})

    if game_key:
        paths = [p for p in paths if p["game"] == game_key]

    # If multiple remain, pick the most likely one.
    return _pick_best(paths)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _settings_path(game_key: str = "") -> Path:
    """Platform-appropriate settings file location."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", "."))
    else:
        base = Path.home() / ".config"
    p = base / "PhantomToolkit"
    p.mkdir(parents=True, exist_ok=True)
    filename = (
        f"backup_settings_{game_key}.json" if game_key else "backup_settings.json"
    )
    return p / filename


_DEFAULT_SETTINGS: dict[str, Any] = {
    "save_directory": "",
    "backup_directory": "",
    "save_file_type": ".sl2",  # extension filter: .sl2 or .co2
    "save_file_name": "",  # specific file selected by user (e.g. "ER0000.sl2")
    "backup_method": 0,  # 0 = interval, 1 = file_watcher
    "auto_backup_interval": 5,  # minutes
    "sleep_between_saves": 10,  # seconds (file watcher)
    "max_backups": 20,
    "quit_to_menu_before_load": False,
    "notification_volume": 50,
    "keybind_save": "",
    "keybind_load": "",
    "keybind_auto_start": "",
    "keybind_auto_stop": "",
}


def _find_save_files(save_dir: str, ext: str) -> list[str]:
    """Find all save files in save_dir matching the given extension."""
    access_dir = _access_path(save_dir or "")
    if not access_dir or not os.path.isdir(access_dir):
        return []

    # Support wildcard/all files
    if ext in ("*", ".*", "", "All Files"):
        return sorted(
            [
                f
                for f in os.listdir(access_dir)
                if os.path.isfile(os.path.join(access_dir, f))
            ]
        )

    ext = ext if ext.startswith(".") else f".{ext}"
    return sorted(
        [
            f
            for f in os.listdir(access_dir)
            if f.lower().endswith(ext.lower())
            and os.path.isfile(os.path.join(access_dir, f))
        ]
    )


def list_save_files(save_dir: str, ext: str) -> list[str]:
    """Public function to list save files for the UI file picker."""
    return _find_save_files(save_dir, ext)


def load_settings(game_key: str = "") -> dict[str, Any]:
    config_mgr = ConfigManager()
    main_key = f"backup_settings_{game_key}" if game_key else "backup_settings"

    # Check if settings exist in central config
    settings = config_mgr.get(main_key)
    if settings is not None:
        return {**_DEFAULT_SETTINGS, **settings}

    # Migration fallback: read old file if it exists
    p = _settings_path(game_key)
    if p.exists():
        try:
            with open(p, "r") as f:
                old_settings = {**_DEFAULT_SETTINGS, **json.load(f)}
            # Save into central config and delete old file
            config_mgr.set(main_key, old_settings)
            with contextlib.suppress(Exception):
                p.unlink()
            return old_settings
        except Exception:
            pass

    return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any], game_key: str = "") -> None:
    config_mgr = ConfigManager()
    main_key = f"backup_settings_{game_key}" if game_key else "backup_settings"
    config_mgr.set(main_key, settings)

    # Apply hotkeys
    _update_hotkeys(settings, game_key)

    # If auto-backup is running for this game, restart it to apply new settings
    global _auto_backup_running_game
    if _auto_backup_running_game == game_key:
        stop_auto_backup()
        start_auto_backup(settings, game_key)

    # Trigger immediate cleanup with new settings
    with contextlib.suppress(Exception):
        _cleanup_old_backups(settings)


# ---------------------------------------------------------------------------
# Pin management
# ---------------------------------------------------------------------------


def _pinned_path(backup_dir: str) -> Path:
    # Under Proton/Wine, we may get POSIX paths from the UI (host bridge).
    # Always translate to a filesystem-accessible path for the current runtime.
    return Path(_access_path(backup_dir)) / "pinned_backups.json"


def _load_pinned(backup_dir: str) -> list[str]:
    p = _pinned_path(backup_dir)
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_pinned(backup_dir: str, pinned: list[str]) -> None:
    p = _pinned_path(backup_dir)
    with open(p, "w") as f:
        json.dump(pinned, f)


# ---------------------------------------------------------------------------
# Backup CRUD
# ---------------------------------------------------------------------------


def list_backups(
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, list[dict]]:
    if settings is None:
        settings = load_settings(game_key)
    backup_dir_ui = settings.get("backup_directory", "")
    backup_dir = _access_path(backup_dir_ui)
    if not backup_dir_ui or not os.path.isdir(backup_dir):
        return {"pinned": [], "regular": []}

    pinned_names = _load_pinned(backup_dir_ui)
    pinned: list[dict] = []
    regular: list[dict] = []

    # Get all zip files with their stats
    entries: list[dict] = []
    for fname in os.listdir(backup_dir):
        if not fname.endswith(".zip"):
            continue
        fpath = os.path.join(backup_dir, fname)
        try:
            stat = os.stat(fpath)
            entries.append(
                {
                    "name": fname,
                    "date": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "isPinned": fname in pinned_names,
                    "hasScreenshot": _zip_has_screenshot(fpath),
                }
            )
        except Exception:
            continue

    # Sort all by mtime descending
    entries.sort(key=lambda x: x["mtime"], reverse=True)

    for entry in entries:
        # Remove helper field
        entry.pop("mtime")
        if entry["name"] in pinned_names:
            pinned.append(entry)
        else:
            regular.append(entry)

    return {"pinned": pinned, "regular": regular}


def _zip_has_screenshot(zip_path: str) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return "screenshot.png" in zf.namelist()
    except Exception:
        return False


def create_backup(
    settings: dict[str, Any] | None = None,
    take_screenshot: bool = True,
    game_key: str = "",
    screenshot_data: bytes | None = None,
) -> dict[str, str]:
    """Create a manual backup. Returns {"name": ..., "path": ...}."""
    if settings is None:
        settings = load_settings(game_key)

    save_dir_ui = settings.get("save_directory", "")
    backup_dir_ui = settings.get("backup_directory", "")
    save_dir = _access_path(save_dir_ui)
    backup_dir = _access_path(backup_dir_ui)
    ext = settings.get("save_file_type", ".sl2")
    selected_file = settings.get("save_file_name", "")

    if not save_dir_ui or not os.path.isdir(save_dir):
        raise RuntimeError(f"Save directory not found: {save_dir_ui}")
    if not backup_dir_ui:
        raise RuntimeError("Backup directory not set")

    os.makedirs(backup_dir, exist_ok=True)

    # If user selected a specific file, use that; otherwise find by extension
    if selected_file:
        save_file_path = os.path.join(save_dir, selected_file)
        if not os.path.isfile(save_file_path):
            raise RuntimeError(f"Selected save file not found: {selected_file}")
        files_to_backup = [selected_file]
    else:
        files_to_backup = _find_save_files(save_dir, ext)
        if not files_to_backup:
            raise RuntimeError(f"No {ext} files found in: {save_dir}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"backup_{timestamp}.zip"
    zip_path = os.path.join(backup_dir, zip_name)
    zip_path_ui = (
        posixpath.join(backup_dir_ui, zip_name)
        if backup_dir_ui.startswith("/")
        else zip_path
    )

    # Use provided screenshot or capture a new one
    if screenshot_data is None and take_screenshot:
        screenshot_data = capture_screenshot()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sf in files_to_backup:
            zf.write(os.path.join(save_dir, sf), sf)
        if screenshot_data:
            zf.writestr("screenshot.png", screenshot_data)

    # Cleanup old backups
    _cleanup_old_backups(settings)

    # Play sound
    _play_notification("save", game_key=game_key)

    # UI doesn't currently use this path, but keep it stable/posix-friendly when possible.
    return {"name": zip_name, "path": zip_path_ui}


def load_backup(
    name: str,
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, str]:
    """Restore a backup zip back to the save directory."""
    if settings is None:
        settings = load_settings(game_key)

    save_dir_ui = settings.get("save_directory", "")
    backup_dir_ui = settings.get("backup_directory", "")
    save_dir = _access_path(save_dir_ui)
    backup_dir = _access_path(backup_dir_ui)

    if not save_dir_ui:
        raise RuntimeError("Save directory not set")
    if not backup_dir_ui:
        raise RuntimeError("Backup directory not set")

    # ---- Centralized "Safe Load" logic ----
    if settings.get("quit_to_menu_before_load", False) and game_key:
        try:
            from phantom_backend.games.registry import GameRegistry
            from phantom_backend.services.actions import ActionsService

            reg = GameRegistry()
            adapter = reg.get(game_key)
            mem = adapter.make_memory()
            try:
                resolver = adapter.make_resolver(mem)
                if mem.process_handle and mem.base_address != 0:
                    ActionsService(
                        mem=mem, resolver=resolver, game_key=game_key
                    ).quit_to_menu()
                    # Wait 1 second (user requested 1s instead of 5s)
                    time.sleep(1)
            finally:
                mem.close()
        except Exception:
            # Game might not be running or attached, proceed anyway
            pass

    zip_path = os.path.join(backup_dir, name)
    if not os.path.isfile(zip_path):
        raise RuntimeError(f"Backup not found: {zip_path}")

    restored: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # Skip non-save files (screenshots)
            if member == "screenshot.png":
                continue
            data = zf.read(member)
            dest = os.path.join(save_dir, member)
            with open(dest, "wb") as f:
                f.write(data)
            restored.append(member)

    if not restored:
        raise RuntimeError("No save files found in backup zip")

    _play_notification("load", game_key=game_key)
    return {"restored": name, "files": restored}


def delete_backup(
    name: str,
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, bool]:
    if settings is None:
        settings = load_settings(game_key)
    backup_dir_ui = settings.get("backup_directory", "")
    backup_dir = _access_path(backup_dir_ui)
    if not backup_dir_ui:
        raise RuntimeError("Backup directory not set")
    fpath = os.path.join(backup_dir, name)
    if os.path.isfile(fpath):
        os.remove(fpath)
        # Also remove from pinned if present
        pinned = _load_pinned(backup_dir_ui)
        if name in pinned:
            pinned.remove(name)
            _save_pinned(backup_dir_ui, pinned)
    return {"deleted": True}


def pin_backup(
    name: str,
    pin: bool,
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, bool]:
    if settings is None:
        settings = load_settings(game_key)
    backup_dir_ui = settings.get("backup_directory", "")
    if not backup_dir_ui:
        raise RuntimeError("Backup directory not set")
    pinned = _load_pinned(backup_dir_ui)
    if pin and name not in pinned:
        pinned.append(name)
    elif not pin and name in pinned:
        pinned.remove(name)
    _save_pinned(backup_dir_ui, pinned)
    return {"pinned": pin}


def rename_backup(
    old_name: str,
    new_name: str,
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, str]:
    if settings is None:
        settings = load_settings(game_key)
    backup_dir_ui = settings.get("backup_directory", "")
    backup_dir = _access_path(backup_dir_ui)
    if not backup_dir_ui:
        raise RuntimeError("Backup directory not set")

    if not new_name.endswith(".zip"):
        new_name += ".zip"

    old_path = os.path.join(backup_dir, old_name)
    new_path = os.path.join(backup_dir, new_name)
    if not os.path.isfile(old_path):
        raise RuntimeError(f"Backup not found: {old_path}")
    if os.path.exists(new_path):
        raise RuntimeError(f"A backup named '{new_name}' already exists")

    os.rename(old_path, new_path)

    # Update pinned list if applicable
    pinned = _load_pinned(backup_dir_ui)
    if old_name in pinned:
        pinned = [new_name if p == old_name else p for p in pinned]
        _save_pinned(backup_dir_ui, pinned)

    return {"old_name": old_name, "new_name": new_name}


def get_screenshot(
    name: str,
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> bytes | None:
    """Extract screenshot PNG from a backup zip. Returns bytes or None."""
    if settings is None:
        settings = load_settings(game_key)
    backup_dir_ui = settings.get("backup_directory", "")
    backup_dir = _access_path(backup_dir_ui)
    if not backup_dir_ui:
        return None
    zip_path = os.path.join(backup_dir, name)
    if not os.path.isfile(zip_path):
        return None
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "screenshot.png" in zf.namelist():
                return zf.read("screenshot.png")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _cleanup_old_backups(settings: dict[str, Any]) -> None:
    backup_dir_ui = settings.get("backup_directory", "")
    backup_dir = _access_path(backup_dir_ui)
    max_backups = settings.get("max_backups", 20)
    if not backup_dir_ui or not os.path.isdir(backup_dir) or max_backups <= 0:
        return

    pinned_names = _load_pinned(backup_dir_ui)
    all_zips = []
    for fname in os.listdir(backup_dir):
        if fname.endswith(".zip") and fname not in pinned_names:
            fpath = os.path.join(backup_dir, fname)
            all_zips.append((os.stat(fpath).st_mtime, fpath, fname))

    all_zips.sort()  # oldest first
    while len(all_zips) > max_backups:
        _, fpath, _ = all_zips.pop(0)
        with contextlib.suppress(Exception):
            os.remove(fpath)


# ---------------------------------------------------------------------------
# Auto-backup thread management
# ---------------------------------------------------------------------------

_auto_backup_thread: threading.Thread | None = None
_auto_backup_stop_event = threading.Event()
_auto_backup_running_game: str = ""
_auto_backup_lock = threading.Lock()


def is_auto_backup_running() -> dict[str, Any]:
    return {
        "running": bool(_auto_backup_running_game),
        "game": _auto_backup_running_game,
    }


def _do_request_save(game_key: str) -> None:
    """Call request_save to force the game to write its save file."""
    if not game_key:
        return
    with contextlib.suppress(Exception):
        from phantom_backend.games.registry import GameRegistry
        from phantom_backend.services.actions import ActionsService

        reg = GameRegistry()
        adapter = reg.get(game_key)
        mem = adapter.make_memory()
        try:
            resolver = adapter.make_resolver(mem)
            ActionsService(mem=mem, resolver=resolver, game_key=game_key).request_save()
        finally:
            mem.close()


def start_auto_backup(
    settings: dict[str, Any] | None = None,
    game_key: str = "",
) -> dict[str, bool]:
    global _auto_backup_thread, _auto_backup_running_game

    if _auto_backup_running_game:
        if _auto_backup_running_game == game_key:
            return {"already_running": True}

        return {
            "already_running": True,
            "error": f"Auto backup already running for {_auto_backup_running_game}",
        }

    if not game_key:
        return {"error": "Game key required"}

    # Initial safety check
    status = _check_game_status(game_key)
    if not status["attached"]:
        return {"error": "Game not attached"}

    if settings is None:
        settings = load_settings(game_key)

    _auto_backup_stop_event.clear()

    method = settings.get("backup_method", 0)

    if method == 0:
        # Interval-based: request save → wait → backup → sleep interval
        interval_min = settings.get("auto_backup_interval", 5)
        interval_sec = max(30, interval_min * 60)  # minimum 30s

        def interval_worker():
            global _auto_backup_running_game
            _auto_backup_running_game = game_key
            try:
                while not _auto_backup_stop_event.is_set():
                    # Safety check before action
                    st = _check_game_status(game_key)
                    if not st["attached"]:
                        break
                    if not st["loaded"]:
                        break

                    try:
                        # 1. Force the game to save
                        _do_request_save(game_key)
                        # 2. Capture screenshot IMMEDIATELY for accuracy
                        ss_data = capture_screenshot()
                        # 3. Wait for save to complete
                        time.sleep(2)
                        # 4. Create the backup
                        create_backup(
                            settings=settings,
                            take_screenshot=True,
                            game_key=game_key,
                            screenshot_data=ss_data,
                        )
                    except Exception:
                        pass
                    _auto_backup_stop_event.wait(interval_sec)
            finally:
                # If we broke out due to detachment/menu, ensure we clean up global state
                if _auto_backup_running_game == game_key:
                    _auto_backup_running_game = ""

        _auto_backup_thread = threading.Thread(target=interval_worker, daemon=True)
        _auto_backup_thread.start()

    else:
        # File watcher mode — request save periodically, then watch for file change
        save_dir = settings.get("save_directory", "")
        ext = settings.get("save_file_type", ".sl2")
        selected_file = settings.get("save_file_name", "")
        sleep_sec = settings.get("sleep_between_saves", 10)

        def _get_watch_mtime() -> float:
            """Get the mtime of the file(s) to watch."""
            if selected_file:
                fp = os.path.join(save_dir, selected_file)
                return os.stat(fp).st_mtime if os.path.isfile(fp) else 0.0
            files = _find_save_files(save_dir, ext)
            if not files:
                return 0.0
            return max(os.stat(os.path.join(save_dir, f)).st_mtime for f in files)

        def watcher_worker():
            global _auto_backup_running_game
            _auto_backup_running_game = game_key
            last_mtime = 0.0
            with contextlib.suppress(Exception):
                last_mtime = _get_watch_mtime()
            try:
                while not _auto_backup_stop_event.is_set():
                    # Safety check before action
                    st = _check_game_status(game_key)
                    if not st["attached"]:
                        break
                    if not st["loaded"]:
                        continue
                    try:
                        # 1. Check if file changed since last backup
                        current_mtime = _get_watch_mtime()

                        if current_mtime > last_mtime:
                            # 2. Change detected!
                            # Note: Screenshot might be slightly late but user prefers passive watching.
                            ss_data = capture_screenshot()

                            last_mtime = current_mtime
                            create_backup(
                                settings=settings,
                                take_screenshot=True,
                                game_key=game_key,
                                screenshot_data=ss_data,
                            )
                            # 3. Respect the user's "cooldown" sleep after a successful backup
                            _auto_backup_stop_event.wait(sleep_sec)

                    except Exception:
                        pass

                    # 4. Fast polling for the change (e.g. every 500ms)
                    _auto_backup_stop_event.wait(0.5)
            finally:
                if _auto_backup_running_game == game_key:
                    _auto_backup_running_game = ""

        _auto_backup_thread = threading.Thread(target=watcher_worker, daemon=True)
        _auto_backup_thread.start()

    _play_notification("auto_start", game_key=game_key)
    return {"started": True, "method": method}


def stop_auto_backup() -> dict[str, bool]:
    global _auto_backup_thread, _auto_backup_running_game

    if not _auto_backup_running_game:
        return {"already_stopped": True}

    _auto_backup_stop_event.set()
    if _auto_backup_thread is not None:
        _auto_backup_thread.join(timeout=5)
        _auto_backup_thread = None

    game_key = _auto_backup_running_game
    _auto_backup_running_game = ""
    _play_notification("auto_stop", game_key=game_key)
    return {"stopped": True}


# ---------------------------------------------------------------------------
# Notification Service (Inline for simplicity or import)
# ---------------------------------------------------------------------------


def _play_notification(event_name: str, game_key: str = "") -> None:
    """Play notification sound with volume control."""
    try:
        from phantom_backend.utils import platform_utils

        # Load settings to get volume
        settings = load_settings(game_key)
        volume = settings.get("notification_volume", 50)

        if volume <= 0:
            return

        sounds = {
            "save": "save_notification.wav",
            "load": "load_notification.wav",
            "auto_start": "start_auto_save_notification.wav",
            "auto_stop": "stop_auto_save_notification.wav",
        }
        fname = sounds.get(event_name)
        if not fname:
            return

        base = Path(__file__).parent.parent / "assets" / "notifications"
        path = base / fname

        if not path.exists():
            return

        platform_utils.play_audio(str(path), volume)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Game Status Helper
# ---------------------------------------------------------------------------


def _check_game_status(game_key: str) -> dict[str, bool]:
    """Check if game is attached and if a player is loaded (not in main menu)."""
    if not game_key:
        return {"attached": False, "loaded": False}

    try:
        from phantom_backend.games.registry import GameRegistry
        from phantom_backend.services.players import PlayerService

        reg = GameRegistry()
        adapter = reg.get(game_key)
        mem = adapter.make_memory()
        try:
            resolver = adapter.make_resolver(mem)
            # 1. Attachment check: make_memory() succeeded, but let's verify base address/handle
            if not mem.process_handle or mem.base_address == 0:
                return {"attached": False, "loaded": False}

            # 2. Player loaded check
            ps = PlayerService(mem=mem, resolver=resolver, game_key=game_key)
            # Checking player 0 is the standard way to see if we are in-game
            local_player = ps.get_player(0)

            return {"attached": True, "loaded": local_player.is_valid}
        finally:
            mem.close()
    except Exception:
        return {"attached": False, "loaded": False}


# ---------------------------------------------------------------------------
# Global Hotkey Management
# ---------------------------------------------------------------------------


def initialize_hotkeys(game_key: str = "") -> None:
    """Load all settings and register hotkeys for all games.

    We always clear and re-register everything to ensure a consistent state
    across different game contexts.
    """
    if keyboard is None:
        return

    # Clear everything once
    with contextlib.suppress(Exception):
        keyboard.unhook_all()

    # 1. Register Global/Default
    settings = load_settings("")
    _register_hotkeys_for_settings(settings, "")

    # 2. Register all game-specific settings from ConfigManager
    config_mgr = ConfigManager()
    for key in config_mgr:
        if key.startswith("backup_settings_"):
            g_key = key[16:]
            if g_key:
                s = load_settings(g_key)
                _register_hotkeys_for_settings(s, g_key)

    # 3. Fallback: Register from legacy files if they still exist
    try:
        conf_dir = _settings_path("").parent
        if conf_dir.exists():
            for f in conf_dir.glob("backup_settings_*.json"):
                fname = f.name
                if fname == "backup_settings.json":
                    continue
                g_key = fname[16:-5]
                if g_key:
                    s = load_settings(g_key)
                    _register_hotkeys_for_settings(s, g_key)
    except Exception:
        pass


def _update_hotkeys(settings: dict[str, Any], game_key: str) -> None:
    """Trigger a full re-initialization of all hotkeys."""
    initialize_hotkeys()


def _register_hotkeys_for_settings(settings: dict[str, Any], game_key: str) -> None:
    """Register keys without clearing."""
    if keyboard is None:
        return

    # Helper wrapper to handle exceptions in callbacks
    def _safe_call(func, *args, **kwargs):
        with contextlib.suppress(Exception):
            func(*args, **kwargs)

    # Save
    kb_save = settings.get("keybind_save", "")
    if kb_save:
        with contextlib.suppress(Exception):
            keyboard.add_hotkey(
                kb_save,
                lambda: _safe_call(
                    create_backup,
                    settings=settings,
                    take_screenshot=True,
                    game_key=game_key,
                ),
            )

    # Load (Load latest backup)
    kb_load = settings.get("keybind_load", "")
    if kb_load:
        with contextlib.suppress(Exception):
            keyboard.add_hotkey(
                kb_load,
                lambda: _safe_call(_load_latest_backup_callback, settings, game_key),
            )

    # Auto Start
    kb_start = settings.get("keybind_auto_start", "")
    if kb_start:
        with contextlib.suppress(Exception):
            keyboard.add_hotkey(
                kb_start,
                lambda: _safe_call(start_auto_backup, settings, game_key),
            )

    # Auto Stop
    kb_stop = settings.get("keybind_auto_stop", "")
    if kb_stop:
        with contextlib.suppress(Exception):
            keyboard.add_hotkey(
                kb_stop,
                lambda: _safe_call(stop_auto_backup),
            )


def _load_latest_backup_callback(settings: dict[str, Any], game_key: str) -> None:
    """Callback to load the most recent backup."""
    # We need to find the latest backup
    backups = list_backups(settings, game_key)
    # Combine pinned and regular, sort by date desc
    all_backups = backups.get("pinned", []) + backups.get("regular", [])
    if not all_backups:
        return

    # Sort by date string desc (YYYY-MM-DD HH:MM:SS)
    all_backups.sort(key=lambda x: x["name"], reverse=True)
    latest = all_backups[0]["name"]

    # Check quit to menu setting embedded in load_backup logic or handle here?
    # load_backup checks settings.
    load_backup(latest, settings, game_key)
