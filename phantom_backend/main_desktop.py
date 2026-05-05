import contextlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def _parse_cli_args(argv: list[str]) -> dict[str, str | bool]:
    """
    Minimal argv parsing (keep dependencies out of the frozen build).

    Supported:
      --no-webview
      --host <host>
      --port <port>
      --launched-by-appimage
    """
    out: dict[str, str | bool] = {}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--no-webview":
            out["no_webview"] = True
            i += 1
            continue
        if a == "--launched-by-appimage":
            out["launched_by_appimage"] = True
            i += 1
            continue
        if a == "--host" and i + 1 < len(argv):
            out["host"] = argv[i + 1]
            i += 2
            continue
        if a == "--port" and i + 1 < len(argv):
            out["port"] = argv[i + 1]
            i += 2
            continue
        i += 1
    return out


def _is_proton_or_wine() -> bool:
    # Steam Proton typically provides these. Keep it heuristic-only.
    keys = (
        "STEAM_COMPAT_DATA_PATH",
        "STEAM_COMPAT_APP_ID",
        "STEAM_COMPAT_CLIENT_INSTALL_PATH",
        "WINEPREFIX",
        "WINELOADERNOEXEC",
    )
    if any(os.environ.get(k) for k in keys):
        return True

    # If the user launches the Windows exe directly under Wine/Proton, those env
    # vars might not be present. Detect Wine via well-known filesystem/registry
    # markers so we still avoid WinForms/webview crashes.
    try:
        if os.path.exists(r"C:\windows\system32\wineboot.exe"):
            return True
    except Exception:
        pass

    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Wine"):
            return True
    except Exception:
        pass

    return False


def _show_error_dialog(title: str, message: str) -> None:
    if IS_WINDOWS:
        # Use a native Win32 MessageBox (works on Windows and usually under Wine/Proton).
        try:
            import ctypes

            MB_ICONERROR = 0x10
            MB_OK = 0x0
            ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | MB_ICONERROR)
            return
        except Exception:
            # If the dialog fails, we still have the log.
            return

    # Linux/macOS: try common dialog helpers; otherwise print to stderr.
    candidates: list[list[str]] = [
        ["zenity", "--error", "--title", title, "--text", message],
        ["kdialog", "--error", message, "--title", title],
        ["xmessage", "-center", "-title", title, message],
    ]
    for cmd in candidates:
        try:
            if not shutil.which(cmd[0]):
                continue
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            continue
    with contextlib.suppress(Exception):
        sys.stderr.write(f"{title}: {message}\n")


def _configure_webview_for_proton() -> None:
    """Apply env tweaks before importing/starting pywebview.

    Important: Under Proton/Wine, pywebview often falls back to the WinForms
    backend (pythonnet + System.Windows.Forms). That frequently crashes due to
    Wine-Mono incompatibilities. We therefore default to disabling the embedded
    webview under Proton and let the Linux launcher open the URL instead.
    """
    if not _is_proton_or_wine():
        return

    # Default: do NOT start the embedded webview under Proton.
    # The AppImage launcher will open the URL and keep this process alive.
    if os.environ.get("PHANTOM_FORCE_WEBVIEW", "0") != "1":
        os.environ.setdefault("PHANTOM_NO_WEBVIEW", "1")


def _detect_steam_root() -> str | None:
    # Mirrors scripts/run_proton_phantomtoolkit.sh and the AppImage AppRun.
    override = os.environ.get("STEAM_ROOT", "").strip()
    if override and os.path.isdir(os.path.join(override, "steamapps")):
        return override

    home = os.path.expanduser("~")
    for p in (
        os.path.join(home, ".steam/steam"),
        os.path.join(home, ".local/share/Steam"),
    ):
        if os.path.isdir(os.path.join(p, "steamapps")):
            return p

    fp = os.path.join(home, ".var/app/com.valvesoftware.Steam/data/Steam")
    if os.path.isdir(os.path.join(fp, "steamapps")):
        return fp

    return None


def _detect_running_game_appid() -> str | None:
    # Heuristic: look for the Windows exe name in Proton/Wine commandlines.
    try:
        out = subprocess.check_output(["ps", "-eo", "args"], text=True, errors="ignore")
    except Exception:
        return None

    lower = out.lower()
    if "eldenring.exe" in lower:
        return "1245620"
    if "darksoulsiii.exe" in lower or "dark souls iii" in lower:
        return "374320"
    return None


def _find_proton(steam_root: str) -> str | None:
    # Prefer Proton - Experimental, then any Proton*/GE-Proton*, then compatibilitytools.d.
    candidates: list[str] = [
        os.path.join(steam_root, "steamapps/common/Proton - Experimental/proton"),
    ]

    common = os.path.join(steam_root, "steamapps/common")
    with contextlib.suppress(Exception):
        if os.path.isdir(common):
            for name in sorted(os.listdir(common)):
                if name.startswith(("Proton", "GE-Proton")):
                    candidates.append(os.path.join(common, name, "proton"))

    ctd = os.path.join(steam_root, "compatibilitytools.d")
    with contextlib.suppress(Exception):
        if os.path.isdir(ctd):
            for name in sorted(os.listdir(ctd)):
                candidates.append(os.path.join(ctd, name, "proton"))

    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _locate_windows_exe() -> str | None:
    """
    Try to locate PhantomToolkit.exe for Linux auto-Proton mode.

    Supported layouts:
    - PHANTOM_WINDOWS_EXE=/path/to/PhantomToolkit.exe
    - PhantomToolkit.exe next to this executable (PyInstaller/Linux bundle)
    - PhantomToolkit.exe next to the AppImage file (if APPIMAGE is set)
    """
    override = os.environ.get("PHANTOM_WINDOWS_EXE", "").strip()
    if override and os.path.isfile(override):
        return override

    exe_name = "PhantomToolkit.exe"

    # Frozen Linux bundle path.
    with contextlib.suppress(Exception):
        here = Path(sys.executable).resolve().parent
        p = str(here / exe_name)
        if os.path.isfile(p):
            return p

    # AppImage runtime mount path (APPDIR points at the mounted AppDir).
    # This is the most common "it should be inside the AppImage" expectation.
    appdir = os.environ.get("APPDIR", "").strip()
    if appdir:
        with contextlib.suppress(Exception):
            candidates = (
                Path(appdir) / exe_name,
                Path(appdir) / "usr" / "bin" / exe_name,
                Path(appdir) / "usr" / "lib" / exe_name,
            )
            for c in candidates:
                if os.path.isfile(str(c)):
                    return str(c)

    # AppImage path (APPIMAGE points to the file on disk, not the mount).
    appimage = os.environ.get("APPIMAGE", "").strip()
    if appimage:
        with contextlib.suppress(Exception):
            p = str(Path(appimage).resolve().parent / exe_name)
            if os.path.isfile(p):
                return p

    return None


def _launch_windows_backend_under_proton(
    *, host: str, port: int
) -> subprocess.Popen[str]:
    steam_root = _detect_steam_root()
    if not steam_root:
        raise RuntimeError("Could not locate Steam (set STEAM_ROOT).")

    appid = (
        os.environ.get("PHANTOM_STEAM_APPID", "").strip()
        or _detect_running_game_appid()
    )
    if not appid:
        raise RuntimeError(
            "No supported game detected. Start Elden Ring or Dark Souls III via Steam (Proton), "
            "or set PHANTOM_STEAM_APPID."
        )

    compatdata = os.environ.get("STEAM_COMPAT_DATA_PATH", "").strip() or os.path.join(
        steam_root, "steamapps", "compatdata", appid
    )
    if not os.path.isdir(compatdata):
        raise RuntimeError(
            f"Compatdata not found: {compatdata}. Launch the game at least once via Steam."
        )

    proton = os.environ.get("PHANTOM_PROTON", "").strip() or (
        _find_proton(steam_root) or ""
    )
    if not proton or not os.path.isfile(proton) or not os.access(proton, os.X_OK):
        raise RuntimeError("Could not find Proton (set PHANTOM_PROTON).")

    win_exe = _locate_windows_exe()
    if not win_exe:
        raise RuntimeError(
            "Could not find PhantomToolkit.exe for Proton mode. "
            "Place PhantomToolkit.exe next to this app, or set PHANTOM_WINDOWS_EXE."
        )

    env = os.environ.copy()
    env["STEAM_COMPAT_APP_ID"] = appid
    env["STEAM_COMPAT_DATA_PATH"] = compatdata
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root
    env["PHANTOM_HOST"] = host
    env["PHANTOM_PORT"] = str(port)
    env.setdefault("PHANTOM_NO_WEBVIEW", "1")

    # Use 'runinprefix' to bypass Proton's steam.exe stub (prevents DLC errors).
    cmd = [
        proton,
        "runinprefix",
        win_exe,
        "--no-webview",
        "--launched-by-appimage",  # semantics: "Linux wrapper opens the URL"
        "--host",
        host,
        "--port",
        str(port),
    ]

    return subprocess.Popen(cmd, env=env)


def _maybe_run_linux_ui_against_proton_backend(*, host: str, port: int) -> bool:
    """
    On native Linux builds, prefer launching the Windows backend under Proton so
    memory writing works (pymem). Returns True if we took over startup.
    """
    if not IS_LINUX:
        return False
    if os.environ.get("PHANTOM_AUTO_PROTON", "1") != "1":
        return False
    if os.environ.get("PHANTOM_FORCE_NATIVE_BACKEND", "0") == "1":
        return False

    # If we don't have the Windows exe available, we can't do Proton mode.
    win_exe = _locate_windows_exe()
    if not win_exe:
        return False

    try:
        proc = _launch_windows_backend_under_proton(host=host, port=port)
    except Exception as e:
        # The user has the Windows build available, so falling back to the native
        # backend is confusing: it will later crash when a write is attempted.
        _show_error_dialog(
            "Phantom Toolkit - Proton Launch Failed",
            "Phantom Toolkit detected a Windows build (PhantomToolkit.exe), but could not\n"
            "launch it under Steam Proton.\n\n"
            f"Error: {e}\n\n"
            "Fix:\n"
            "- Start the game via Steam (Proton) first, then launch Phantom Toolkit, or\n"
            "- Set STEAM_ROOT / PHANTOM_PROTON / PHANTOM_STEAM_APPID if detection fails.\n\n"
            "You can force native mode (read-only) by setting PHANTOM_FORCE_NATIVE_BACKEND=1.",
        )
        return True

    url = f"http://{host}:{port}"
    try:
        _wait_for_server(host=host, port=port, timeout_s=20.0)
    except Exception as e:
        _show_error_dialog(
            "Phantom Toolkit - Proton Backend Error",
            "Started the Proton backend but it did not become reachable.\n\n"
            f"Tried: {url}\n"
            f"Error: {e}",
        )
        with contextlib.suppress(Exception):
            proc.terminate()
        return True

    # Run a native UI against the Proton backend.
    try:
        import webview

        webview.create_window(
            "Phantom Toolkit", url, width=1600, height=950, resizable=True
        )
        webview.start(debug=False)
    finally:
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=3)
        with contextlib.suppress(Exception):
            proc.kill()

    return True


def _port_is_free(port: int, host: str) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except Exception:
        return False


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def _wait_for_server(*, host: str, port: int, timeout_s: float = 15.0) -> None:
    """
    Block until the local server responds, or raise on timeout.

    This avoids a common packaged-app failure mode where the webview opens before
    uvicorn is listening (or uvicorn crashed, but the console is hidden).
    """
    import json
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    last_err: str | None = None
    url = f"http://{host}:{port}/ping"

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.75) as resp:
                status = getattr(resp, "status", 200)
                content_type = (resp.headers.get("content-type") or "").lower()
                body = resp.read().decode("utf-8", errors="replace")

            # Any HTTP response means uvicorn is listening and the app is serving.
            # Prefer the JSON ping, but don't block startup if the SPA route intercepts it.
            if status and int(status) < 500:
                if "application/json" in content_type:
                    data = json.loads(body)
                    if isinstance(data, dict) and data.get("status") == "ok":
                        return
                    last_err = f"Unexpected JSON /ping response: {body[:200]}"
                else:
                    # Example failure mode: `/ping` returns SPA HTML due to a routing mismatch.
                    pass
                    return

            last_err = f"HTTP {status} /ping response: {body[:200]}"
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_err = str(e)
        time.sleep(0.15)

    raise TimeoutError(f"Server not reachable at {url} (last error: {last_err})")


def _ensure_stdio_streams() -> None:
    """
    PyInstaller `--windowed` builds may set sys.stdout/sys.stderr to None.
    Uvicorn's default logging formatter calls `isatty()` on these streams.
    """
    # These file handles intentionally stay open for the app lifetime.
    with contextlib.suppress(Exception):
        if sys.stdout is None:
            sys.stdout = open(  # noqa: SIM115
                os.devnull, "w", encoding="utf-8"
            )  # type: ignore[assignment]
        if sys.stderr is None:
            sys.stderr = open(  # noqa: SIM115
                os.devnull, "w", encoding="utf-8"
            )  # type: ignore[assignment]


def run_server(port: int, *, host: str, failed: threading.Event, error_out: list[str]):
    # Set the static directory based on where we are running
    try:
        _ensure_stdio_streams()

        if getattr(sys, "frozen", False):
            # Running in a bundle
            base_dir = sys._MEIPASS
            static_dir = os.path.join(base_dir, "gui_dist")
        else:
            # Running locally (assuming run from project root)
            static_dir = os.path.join(os.getcwd(), "gui", "dist")

        os.environ["PHANTOM_STATIC_DIR"] = static_dir
        os.environ["PHANTOM_HOST"] = host
        os.environ["PHANTOM_PORT"] = str(port)

        # Disable uvicorn logging to console (this app is usually windowed).
        config = uvicorn.Config(
            "phantom_backend.api.app:create_app",
            host=host,
            port=port,
            factory=True,
            log_level="error",
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        failed.set()
        error_out.append(str(e))
        # trace back will be shown in the error dialog by main() if thread dies early


def main():
    cli = _parse_cli_args(sys.argv)
    if cli.get("launched_by_appimage"):
        os.environ.setdefault("PHANTOM_LAUNCHED_BY_APPIMAGE", "1")
    if cli.get("no_webview"):
        os.environ["PHANTOM_NO_WEBVIEW"] = "1"
    if isinstance(cli.get("host"), str) and cli["host"]:
        os.environ["PHANTOM_HOST"] = str(cli["host"])
    if isinstance(cli.get("port"), str) and str(cli["port"]).isdigit():
        os.environ["PHANTOM_PORT"] = str(cli["port"])

    _configure_webview_for_proton()
    host = os.getenv("PHANTOM_HOST", "127.0.0.1")

    # Allow launchers to preselect a stable port (useful when the embedded webview
    # is disabled and the launcher will open the URL itself).
    req_port_raw = os.environ.get("PHANTOM_PORT", "").strip()
    if req_port_raw.isdigit() and int(req_port_raw) > 0:
        port = int(req_port_raw)
        if not _port_is_free(port, host):
            raise RuntimeError(
                f"Requested PHANTOM_PORT={port} is not available on host {host}"
            )
    else:
        port = find_free_port()

    # Native Linux backend mode cannot use the Windows-only injection/memory APIs.
    # If PhantomToolkit.exe is available, automatically run it under the game's
    # Steam Proton prefix and render the UI natively on Linux.
    if _maybe_run_linux_ui_against_proton_backend(host=host, port=port):
        return

    failed = threading.Event()
    server_error: list[str] = []

    # Start server in a thread
    t = threading.Thread(
        target=run_server,
        args=(port,),
        kwargs={"host": host, "failed": failed, "error_out": server_error},
        daemon=True,
    )
    t.start()

    # Block until the backend is reachable (or we can present a clear error).
    try:
        _wait_for_server(host=host, port=port, timeout_s=20.0)
    except Exception as e:
        msg = (
            "Phantom Toolkit backend did not start correctly, so the UI cannot load.\n\n"
            f"Tried: http://{host}:{port}\n"
            f"Error: {e}"
        )
        if server_error:
            msg += f"\n\nServer thread error: {server_error[-1]}"

        _show_error_dialog("Phantom Toolkit - Server Error", msg)
        raise

    try:
        # Import after env tweaks (esp. PYWEBVIEW_GUI).
        if os.environ.get("PHANTOM_NO_WEBVIEW", "0") == "1":
            url = f"http://{host}:{port}"
            # If launched by the AppImage wrapper, it will open the URL itself.
            if os.environ.get("PHANTOM_LAUNCHED_BY_APPIMAGE", "0") != "1":
                _show_error_dialog(
                    "Phantom Toolkit",
                    "Phantom Toolkit is running (server-only mode).\n\n"
                    f"Open this URL in your browser:\n{url}\n\n"
                    "If you want to try the embedded UI under Proton, set PHANTOM_FORCE_WEBVIEW=1.",
                )
            # Keep process alive while the server thread runs.
            while not failed.is_set():
                time.sleep(0.5)
            raise RuntimeError(server_error[-1] if server_error else "Server stopped")

        import webview

        webview.create_window(
            "Phantom Toolkit",
            f"http://{host}:{port}",
            width=1600,
            height=950,
            resizable=True,
        )

        start_kwargs: dict[str, object] = {"debug": False}
        gui = os.environ.get("PYWEBVIEW_GUI", "").strip()
        if gui:
            start_kwargs["gui"] = gui
        webview.start(**start_kwargs)
    except Exception as e:
        msg = (
            "Failed to start PhantomToolkit desktop UI.\n\n"
            f"Error: {e}\n\n"
            "If you are running on Linux via Steam Proton/Wine, install/enable a Proton build that\n"
            "can run QtWebEngine, and try again."
        )
        _show_error_dialog("Phantom Toolkit - UI Error", msg)
        raise


if __name__ == "__main__":
    main()
