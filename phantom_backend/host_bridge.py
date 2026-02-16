"""
Linux host bridge for the AppImage/Proton build.

Why this exists:
- In AppImage mode the FastAPI backend runs inside Proton/Wine (Windows Python).
- We still want *native Linux* dialogs (directory picker) and native screenshot capture,
  especially on Wayland.

This process runs natively on Linux and exposes a tiny HTTP API on localhost:
- GET /ping
- GET /browse_directory?initial_dir=...
- GET /screenshot  (PNG bytes)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from http.server import ThreadingHTTPServer  # type: ignore
except ImportError:
    import socketserver

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):  # type: ignore
        pass


_DIALOG_LOCK = threading.Lock()
_CAPTURE_LOCK = threading.Lock()

# Queue for running tasks on the main thread (required for Qt dialogs)
_MAIN_QUEUE: queue.Queue = queue.Queue()


@dataclass
class _LastCapture:
    ts_iso: str = ""
    method: str = ""
    size_bytes: int = 0
    note: str = ""


_LAST_CAPTURE = _LastCapture()


def _child_env() -> dict[str, str]:
    """Sanitize env for calling host tools from inside AppImage.

    AppImage sets `LD_LIBRARY_PATH` and various Qt paths which can break system
    binaries like `spectacle` (leading to black/tiny PNGs).
    """
    env = dict(os.environ)
    for k in (
        "LD_LIBRARY_PATH",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PHANTOM_LAUNCHED_BY_APPIMAGE",
    ):
        env.pop(k, None)
    return env


def _set_last_capture(*, method: str, size_bytes: int, note: str = "") -> None:
    with _CAPTURE_LOCK:
        _LAST_CAPTURE.ts_iso = datetime.now(UTC).isoformat()
        _LAST_CAPTURE.method = method
        _LAST_CAPTURE.size_bytes = int(size_bytes)
        _LAST_CAPTURE.note = note


def _get_last_capture() -> _LastCapture:
    with _CAPTURE_LOCK:
        return _LastCapture(
            ts_iso=_LAST_CAPTURE.ts_iso,
            method=_LAST_CAPTURE.method,
            size_bytes=_LAST_CAPTURE.size_bytes,
            note=_LAST_CAPTURE.note,
        )


def _linux_play_wav_file(path: str) -> None:
    # Prefer PipeWire/Pulse, then ALSA.
    if _which("pw-play"):
        subprocess.run(["pw-play", path], check=False, env=_child_env())
        return
    if _which("paplay"):
        subprocess.run(["paplay", path], check=False, env=_child_env())
        return
    if _which("aplay"):
        subprocess.run(["aplay", "-q", path], check=False, env=_child_env())
        return


def _linux_audio_player_tools() -> dict[str, bool]:
    return {
        "pw-play": bool(_which("pw-play")),
        "paplay": bool(_which("paplay")),
        "aplay": bool(_which("aplay")),
    }


def _linux_has_audio_player() -> bool:
    tools = _linux_audio_player_tools()
    return any(tools.values())


def _scale_wav_bytes(data: bytes, volume: int) -> bytes:
    if volume >= 100:
        return data
    try:
        import struct
        from io import BytesIO

        with wave.open(BytesIO(data), "rb") as wav_in:
            params = wav_in.getparams()
            frames = wav_in.readframes(params.nframes)
            if params.sampwidth != 2:
                return data
            fmt = f"<{params.nframes * params.nchannels}h"
            samples = struct.unpack(fmt, frames)
            factor = volume / 100.0
            scaled = [max(min(int(s * factor), 32767), -32768) for s in samples]
            frames2 = struct.pack(fmt, *scaled)

        out = BytesIO()
        with wave.open(out, "wb") as wav_out:
            wav_out.setparams(params)
            wav_out.writeframes(frames2)
        return out.getvalue()
    except Exception:
        return data


def _play_wav_bytes_async(data: bytes, *, volume: int) -> None:
    def _worker():
        fd, tmp = tempfile.mkstemp(prefix="phantom_sound_", suffix=".wav")
        os.close(fd)
        try:
            blob = _scale_wav_bytes(data, volume)
            with open(tmp, "wb") as f:
                f.write(blob)
            _linux_play_wav_file(tmp)
        finally:
            with contextlib.suppress(Exception):
                os.remove(tmp)

    threading.Thread(target=_worker, daemon=True).start()


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY", "").strip()
    )


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _run_on_main_thread(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run a function on the main thread and wait for result."""
    # If we are already on the main thread, run directly (rare in this threading model)
    if threading.current_thread() is threading.main_thread():
        return func(*args, **kwargs)

    result_container = {}
    event = threading.Event()

    def wrapper():
        try:
            result_container["result"] = func(*args, **kwargs)
        except Exception as e:
            result_container["error"] = e
        finally:
            event.set()

    _MAIN_QUEUE.put(wrapper)
    event.wait()

    if "error" in result_container:
        raise result_container["error"]
    return result_container.get("result")


def _qt_pick_directory(*, initial_dir: str, title: str) -> str | None:
    """Qt fallback picker (works even without zenity/kdialog/yad)."""

    def _inner():
        try:
            from PySide6.QtWidgets import QApplication, QFileDialog

            QApplication.instance() or QApplication([])
            start_dir = initial_dir or os.path.expanduser("~")
            path = QFileDialog.getExistingDirectory(None, title, start_dir)
            return path or None
        except Exception:
            return None

    return _run_on_main_thread(_inner)


def _qt_save_file(*, initial_dir: str, default_name: str, title: str) -> str | None:
    """Qt fallback save dialog (works even without zenity/kdialog/yad)."""

    def _inner():
        try:
            from PySide6.QtWidgets import QApplication, QFileDialog

            QApplication.instance() or QApplication([])
            start_dir = initial_dir or os.path.expanduser("~")
            suggested = os.path.join(start_dir, default_name)
            path, _ = QFileDialog.getSaveFileName(
                None,
                title,
                suggested,
                "JSON Files (*.json);;All Files (*)",
            )
            return path or None
        except Exception:
            return None

    return _run_on_main_thread(_inner)


def _run_pick_dir_dialog(initial_dir: str = "") -> str | None:
    initial_dir = initial_dir.strip()
    if initial_dir and not os.path.isdir(initial_dir):
        initial_dir = ""

    title = "Select Folder"

    # Detect Preference
    is_kde = "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    # Define runners
    def run_zenity():
        if not _which("zenity"):
            return -1, None
        filename = os.path.join(initial_dir, "") if initial_dir else ""
        cmd = ["zenity", "--file-selection", "--directory", "--title", title]
        if filename:
            cmd += ["--filename", filename]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    def run_kdialog():
        if not _which("kdialog"):
            return -1, None
        cmd = ["kdialog", "--getexistingdirectory"]
        if initial_dir:
            cmd.append(initial_dir)
        cmd += ["--title", title]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    def run_yad():
        if not _which("yad"):
            return -1, None
        filename = os.path.join(initial_dir, "") if initial_dir else ""
        cmd = ["yad", "--file-selection", "--directory", "--title", title]
        if filename:
            cmd += ["--filename", filename]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    # Order based on DE
    attempts = []
    if is_kde:
        attempts = [run_kdialog, run_zenity, run_yad]
    else:
        attempts = [run_zenity, run_kdialog, run_yad]

    for runner in attempts:
        code, out = runner()
        if code == 0:
            return out or None
        if code == 1:
            # User cancelled explicitly. Do not fall through to next tool.
            return None
        # code < 0 or > 1 usually implies tool missing or crashed; try next.

    return _qt_pick_directory(initial_dir=initial_dir, title=title)


def _run_save_file_dialog(
    initial_dir: str = "", default_name: str = "build.json"
) -> str | None:
    initial_dir = initial_dir.strip()
    if initial_dir and not os.path.isdir(initial_dir):
        initial_dir = ""

    default_name = (default_name or "build.json").strip()
    if not default_name.lower().endswith(".json"):
        default_name += ".json"

    title = "Save File"

    is_kde = "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    def run_zenity():
        if not _which("zenity"):
            return -1, None
        filename = default_name
        if initial_dir:
            filename = os.path.join(initial_dir, default_name)
        cmd = [
            "zenity",
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            "--title",
            title,
            "--filename",
            filename,
        ]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    def run_kdialog():
        if not _which("kdialog"):
            return -1, None
        suggested = default_name
        if initial_dir:
            suggested = os.path.join(initial_dir, default_name)
        cmd = ["kdialog", "--getsavefilename", suggested, "--title", title]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    def run_yad():
        if not _which("yad"):
            return -1, None
        filename = default_name
        if initial_dir:
            filename = os.path.join(initial_dir, default_name)
        cmd = [
            "yad",
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            "--title",
            title,
            "--filename",
            filename,
        ]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
        return r.returncode, (r.stdout or "").strip()

    attempts = []
    if is_kde:
        attempts = [run_kdialog, run_zenity, run_yad]
    else:
        attempts = [run_zenity, run_kdialog, run_yad]

    for runner in attempts:
        code, out = runner()
        if code == 0:
            return out or None
        if code == 1:
            return None

    return _qt_save_file(
        initial_dir=initial_dir, default_name=default_name, title=title
    )


def _get_linux_primary_monitor_geometry() -> tuple[int, int, int, int] | None:
    """Detect primary monitor geometry (x, y, width, height) on Linux."""
    # 1. Try kscreen-doctor (KDE)
    if _which("kscreen-doctor"):
        try:
            result = subprocess.run(
                ["kscreen-doctor", "-o"],
                capture_output=True,
                text=True,
                timeout=3,
                env=_child_env(),
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

    # 2. Try xrandr (X11)
    if _which("xrandr"):
        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True,
                text=True,
                timeout=3,
                env=_child_env(),
            )
            if result.returncode == 0:
                # Look for " primary " in the output
                import re

                for line in result.stdout.splitlines():
                    if " primary " in line:
                        # Format: "DP-3 connected primary 2560x1440+1920+0 ..."
                        # match 2560x1440+1920+0
                        m = re.search(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
                        if m:
                            w, h, x, y = map(int, m.groups())
                            return x, y, w, h
        except Exception:
            pass

    return None


def _resize_png_bytes(
    png_bytes: bytes,
    *,
    max_width: int = 1280,
    geom: tuple[int, int, int, int] | None = None,
) -> bytes:
    # Keep this optional so the bridge can still work if PIL isn't available.
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(png_bytes))

        # Check if we need to crop to a specific monitor
        if geom:
            x, y, w, h = geom
            img_w, img_h = img.size
            # Image.crop uses (left, top, right, bottom)
            # Ensure coordinates are within image bounds
            left = max(0, min(x, img_w))
            top = max(0, min(y, img_h))
            right = max(left, min(x + w, img_w))
            bottom = max(top, min(y + h, img_h))
            if right > left and bottom > top:
                img = img.crop((left, top, right, bottom))

        w, h = img.size
        if w > max_width and w > 0:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return png_bytes


def _try_screenshot_cmd(
    cmd: list[str], out_file: str, geom: tuple[int, int, int, int] | None = None
) -> bytes | None:
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=15, check=True, env=_child_env()
        )
        # Some tools return before the file is fully flushed; wait briefly.
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                break
            time.sleep(0.05)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
            with open(out_file, "rb") as f:
                data = f.read()
            return _resize_png_bytes(data, max_width=1280, geom=geom)
    except Exception:
        return None
    finally:
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
        except Exception:
            pass
    return None


def _capture_screenshot_png() -> bytes | None:
    # Screenshot strategy:
    # - Wayland: prefer KDE Spectacle, then xdg-desktop-portal. Avoid Qt grabWindow on Wayland
    #   (commonly returns tiny/black PNGs).
    # - X11: prefer Spectacle, then scrot, then Qt fallback.
    wayland = _is_wayland()
    geom = _get_linux_primary_monitor_geometry()

    fd, tmp_path = tempfile.mkstemp(prefix="phantom_host_ss_", suffix=".png")
    os.close(fd)
    try:
        # 1) Spectacle (KDE) - generally reliable on KDE Wayland/X11.
        if _which("spectacle"):
            # Keep this minimal: try a common legacy form and a newer long-flag form.
            spectacle_cmds = [
                ["spectacle", "-f", "-b", "-n", "-o", tmp_path],
                [
                    "spectacle",
                    "--background",
                    "--nonotify",
                    "--fullscreen",
                    "--output",
                    tmp_path,
                ],
            ]
            for cmd in spectacle_cmds:
                data = _try_screenshot_cmd(cmd, tmp_path, geom=geom)
                if data:
                    _set_last_capture(method="spectacle", size_bytes=len(data))
                    return data

        # 1b) grim (generic Wayland) - common on wlroots-based compositors.
        if wayland and _which("grim"):
            data = _try_screenshot_cmd(["grim", tmp_path], tmp_path, geom=geom)
            if data:
                _set_last_capture(method="grim", size_bytes=len(data))
                return data

        # 2) scrot (X11)
        if not wayland and _which("scrot"):
            data = _try_screenshot_cmd(["scrot", tmp_path], tmp_path, geom=geom)
            if data:
                _set_last_capture(method="scrot", size_bytes=len(data))
                return data

        # 3) xdg-desktop-portal fallback (Wayland-friendly, cross-desktop)
        if wayland:
            data = _portal_capture_screenshot_png(timeout_s=15.0)
            if data:
                _set_last_capture(method="xdg-desktop-portal", size_bytes=len(data))
                return data

        # 4) Qt fallback (X11 only).
        if not wayland:
            data = _qt_capture_screenshot_png(geom=geom)
            if data:
                _set_last_capture(method="qt", size_bytes=len(data))
                return data

        _set_last_capture(
            method="none",
            size_bytes=0,
            note=(
                "no_capture_backend_succeeded_wayland"
                if wayland
                else "no_capture_backend_succeeded_x11"
            ),
        )
        return None
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _qt_capture_screenshot_png(
    geom: tuple[int, int, int, int] | None = None,
) -> bytes | None:
    def _inner():
        try:
            from PySide6.QtCore import QBuffer, QByteArray
            from PySide6.QtGui import QGuiApplication

            QGuiApplication.instance() or QGuiApplication([])
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return None
            pix = screen.grabWindow(0)
            img = pix.toImage()
            if img.isNull():
                return None
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            ok = img.save(buf, "PNG")
            buf.close()
            if not ok:
                return None
            raw = bytes(ba)
            if len(raw) < 6000:
                return None
            out = _resize_png_bytes(raw, max_width=1280, geom=geom)
            if len(out) < 6000:
                return None
            return out
        except Exception:
            return None

    return _run_on_main_thread(_inner)


def _portal_capture_screenshot_png(*, timeout_s: float = 15.0) -> bytes | None:
    """Use xdg-desktop-portal Screenshot API via gdbus/dbus-monitor.

    This is the most compatible way to screenshot on Wayland across GNOME/KDE/etc.
    Requires `gdbus` and `dbus-monitor` to be available on the host.
    """
    if not _which("gdbus") or not _which("dbus-monitor"):
        return None

    token = f"phantom{os.getpid()}{int(time.time() * 1000)}"
    # interactive=true makes the portal reliably return a real capture on more setups.
    opts = f"{{'handle_token': <'{token}'>, 'interactive': <true>}}"

    # Start monitoring signals for the request response.
    monitor = subprocess.Popen(
        [
            "dbus-monitor",
            "--session",
            "type='signal',interface='org.freedesktop.portal.Request',member='Response'",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=_child_env(),
    )
    try:
        # Trigger the screenshot request.
        call = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.portal.Desktop",
                "--object-path",
                "/org/freedesktop/portal/desktop",
                "--method",
                "org.freedesktop.portal.Screenshot",
                "Screenshot",
                "",
                opts,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=_child_env(),
        )
        if call.returncode != 0:
            return None

        # Extract request object path from output: (objectpath '/org/...',)
        out = (call.stdout or "").strip()
        # naive parse: look for "/org/freedesktop/portal/desktop/request/"
        marker = "/org/freedesktop/portal/desktop/request/"
        idx = out.find(marker)
        if idx < 0:
            return None
        req_path = out[idx:].split("'")[0].split(",")[0].strip()

        # Wait for the response containing a file URI.
        deadline = time.time() + timeout_s
        uri: str | None = None
        current_path: str | None = None

        assert monitor.stdout is not None
        while time.time() < deadline:
            line = monitor.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            line = line.strip()
            if line.startswith("path "):
                current_path = line.split(" ", 1)[1].strip().strip('"')
                continue
            if current_path != req_path:
                continue
            # dbus-monitor prints string values as: string "file:///..."
            if 'string "file://' in line:
                uri = line.split('string "', 1)[1].split('"', 1)[0]
                break

        if not uri:
            return None

        # Convert file:// URI to local path
        from urllib.parse import unquote, urlparse

        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = unquote(parsed.path)
        if not path or not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            data = f.read()
        if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        if len(data) < 6000:
            return None
        return _resize_png_bytes(data, max_width=1280)
    finally:
        with contextlib.suppress(Exception):
            monitor.terminate()
        with contextlib.suppress(Exception):
            monitor.kill()


class _Handler(BaseHTTPRequestHandler):
    server_version = "PhantomHostBridge/1.0"

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, code: int, data: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/ping":
            self._send_bytes(200, b"ok", "text/plain; charset=utf-8")
            return

        if path == "/status":
            last = _get_last_capture()
            tools = {
                "spectacle": bool(_which("spectacle")),
                "grim": bool(_which("grim")),
                "gnome-screenshot": bool(_which("gnome-screenshot")),
                "scrot": bool(_which("scrot")),
                "gdbus": bool(_which("gdbus")),
                "dbus-monitor": bool(_which("dbus-monitor")),
            }
            self._send_json(
                200,
                {
                    "wayland": _is_wayland(),
                    "tools": tools,
                    "audio_tools": _linux_audio_player_tools(),
                    "last_capture": {
                        "ts": last.ts_iso,
                        "method": last.method,
                        "size_bytes": last.size_bytes,
                        "note": last.note,
                    },
                },
            )
            return

        if path == "/browse_directory":
            initial_dir = (qs.get("initial_dir", [""])[0] or "").strip()
            # Do not queue multiple dialogs; if one is already open, report busy.
            # NOTE: With ThreadingHTTPServer, multiple requests come in parallel.
            # usage of blocking=False prevents sequential stacking.
            if not _DIALOG_LOCK.acquire(blocking=False):
                self._send_json(409, {"path": None, "error": "dialog_busy"})
                return
            try:
                chosen = _run_pick_dir_dialog(initial_dir)
            finally:
                with contextlib.suppress(Exception):
                    _DIALOG_LOCK.release()
            self._send_json(200, {"path": chosen})
            return

        if path == "/save_file":
            initial_dir = (qs.get("initial_dir", [""])[0] or "").strip()
            default_name = (
                qs.get("default_name", ["build.json"])[0] or "build.json"
            ).strip()
            if not _DIALOG_LOCK.acquire(blocking=False):
                self._send_json(409, {"path": None, "error": "dialog_busy"})
                return
            try:
                chosen = _run_save_file_dialog(initial_dir, default_name)
            finally:
                with contextlib.suppress(Exception):
                    _DIALOG_LOCK.release()
            self._send_json(200, {"path": chosen})
            return

        if path == "/screenshot":
            data = _capture_screenshot_png()
            if not data:
                last = _get_last_capture()
                tools = {
                    "spectacle": bool(_which("spectacle")),
                    "grim": bool(_which("grim")),
                    "gnome-screenshot": bool(_which("gnome-screenshot")),
                    "scrot": bool(_which("scrot")),
                    "gdbus": bool(_which("gdbus")),
                    "dbus-monitor": bool(_which("dbus-monitor")),
                }
                self._send_json(
                    404,
                    {
                        "error": "no_screenshot",
                        "wayland": _is_wayland(),
                        "tools": tools,
                        "last_capture": {
                            "ts": last.ts_iso,
                            "method": last.method,
                            "size_bytes": last.size_bytes,
                            "note": last.note,
                        },
                    },
                )
                return
            last = _get_last_capture()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if last.method:
                self.send_header("X-Phantom-Capture-Method", last.method)
            self.end_headers()
            self.wfile.write(data)
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/play_sound":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except Exception:
                length = 0
            data = self.rfile.read(length) if length > 0 else b""
            try:
                volume = int((qs.get("volume", ["100"])[0] or "100").strip())
            except Exception:
                volume = 100
            volume = max(0, min(100, volume))
            if not data:
                self._send_json(400, {"ok": False, "error": "no_data"})
                return
            if not _linux_has_audio_player():
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "error": "no_audio_player",
                        "audio_tools": _linux_audio_player_tools(),
                    },
                )
                return

            _play_wav_bytes_async(data, volume=volume)
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"error": "not_found"})

    def log_message(self, fmt: str, *args: Any) -> None:  # silence default stdout logs
        return


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    args = _parse_args(argv)

    # Use ThreadingHTTPServer to handle requests in background threads.
    # This prevents one blocking request (dialog) from stalling all others.
    httpd = ThreadingHTTPServer((str(args.host), int(args.port)), _Handler)
    print(f"PhantomHostBridge started on {args.host}:{args.port}", flush=True)  # noqa: T201

    # Run the server in a separate daemon thread so we can consume the queue
    # on the Main Thread (crucial for Qt correctness).
    server_thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True
    )
    server_thread.start()

    try:
        # Main thread loop: process queue items forever
        while True:
            try:
                # Wait for a task or sleep to allow interrupt
                task = _MAIN_QUEUE.get(timeout=0.1)
                task()
            except queue.Empty:
                pass
            if not server_thread.is_alive():
                break
    except KeyboardInterrupt:
        return 0
    finally:
        with contextlib.suppress(Exception):
            httpd.server_close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
