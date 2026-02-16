"""Platform-specific utilities."""

import contextlib
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request
import wave
from pathlib import Path


def play_audio(file_path: str, volume: int = 100) -> None:
    """
    Play an audio file with volume control.
    Supports Windows (PowerShell) and Linux (aplay via subprocess).
    """
    if volume <= 0:
        return

    path_obj = Path(file_path)
    if not path_obj.exists():
        return

    # If running under Proton/Wine (platform reports Windows) but we have a native host bridge,
    # forward sound playback to the Linux host so it actually plays.
    host_bridge = os.environ.get("PHANTOM_HOST_BRIDGE_URL", "").strip().rstrip("/")
    if host_bridge and platform.system() == "Windows":
        try:
            data = path_obj.read_bytes()
            q = urllib.parse.urlencode({"volume": str(int(volume))})
            req = urllib.request.Request(
                f"{host_bridge}/play_sound?{q}",
                data=data,
                method="POST",
                headers={"Content-Type": "application/octet-stream"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310
                raw = resp.read() or b""
                status = getattr(resp, "status", 200)
            if status != 200:
                raise RuntimeError(f"host_bridge_play_sound_http_{status}")
            # Bridge returns JSON: {"ok": true} or {"ok": false, "error": "..."}
            try:
                import json

                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if payload and payload.get("ok") is False:
                    raise RuntimeError(
                        f"host_bridge_play_sound_failed:{payload.get('error')}"
                    )
            except Exception:
                # If JSON parse fails, assume it played; don't break normal flow.
                pass
            return
        except Exception:
            # Fall back to the regular behavior.
            pass

    try:
        # If volume is 100, just play directly (optimization)
        if volume == 100:
            _play_file(str(path_obj))
            return

        # Otherwise, scale audio via temp file
        with wave.open(str(path_obj), "rb") as wav:
            params = wav.getparams()
            frames = wav.readframes(params.nframes)

            # Only support 16-bit (width=2) for simple scaling
            if params.sampwidth == 2:
                fmt = f"<{params.nframes * params.nchannels}h"
                samples = struct.unpack(fmt, frames)
                factor = volume / 100.0

                # Scaling
                scaled = [max(min(int(s * factor), 32767), -32768) for s in samples]
                frames = struct.pack(fmt, *scaled)

                # Write to temporary file
                fd, tmp_path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)

                with wave.open(tmp_path, "wb") as out_wav:
                    out_wav.setparams(params)
                    out_wav.writeframes(frames)

                # Play scaled
                _play_file(tmp_path, cleanup=True)
            else:
                _play_file(str(path_obj))

    except Exception:
        # Fallback
        _play_file(str(path_obj))


def _play_file(file_path: str, cleanup: bool = False) -> None:
    """Play the file in a background thread."""

    def _worker(p: str):
        try:
            with contextlib.suppress(Exception):
                system = platform.system()
                if system == "Windows":
                    # PowerShell .NET SoundPlayer
                    cmd = f'(New-Object System.Media.SoundPlayer "{p}").PlaySync()'
                    subprocess.run(
                        ["powershell", "-c", cmd],
                        check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                elif system == "Linux":
                    # Prefer PipeWire/Pulse, then ALSA.
                    if shutil.which("pw-play"):
                        subprocess.run(["pw-play", p], check=False)
                    elif shutil.which("paplay"):
                        subprocess.run(["paplay", p], check=False)
                    else:
                        subprocess.run(["aplay", "-q", p], check=False)
                else:
                    # Fallback for others (MacOS/BSD?)
                    pass
        finally:
            if cleanup:
                with contextlib.suppress(Exception):
                    os.remove(p)

    t = threading.Thread(target=_worker, args=(file_path,), daemon=True)
    t.start()


def browse_directory(initial_dir: str = "") -> str | None:
    """
    Open a system native folder browser dialog.
    Returns the selected path or None if cancelled/failed.
    """

    with contextlib.suppress(Exception):
        # Use tkinter for cross-platform dialogs where possible (available in standard python)
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()  # Hide the main window
        root.attributes("-topmost", True)  # Make dialog appear on top

        path = filedialog.askdirectory(initialdir=initial_dir)
        root.destroy()

        return path if path else None

    return None


def save_file_dialog(
    initial_dir: str = "", default_name: str = "build.json"
) -> str | None:
    """
    Open a system native file save dialog.
    Returns the selected path or None if cancelled/failed.
    """

    with contextlib.suppress(Exception):
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        # Ensure initial_dir exists, otherwise Tkinter might default to documents
        if initial_dir and not os.path.exists(initial_dir):
            initial_dir = ""

        path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        root.destroy()

        return path if path else None

    return None
