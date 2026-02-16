#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _port_is_free(port: int) -> bool:
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", int(port)))
        s.close()
        return True
    except Exception:
        return False


def _pick_free_port() -> int:
    # Prefer OS-assigned free port.
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
        s.close()
        return port
    except Exception:
        # Some sandboxed environments disallow sockets. Fall back to a range.
        for port in range(8765, 8785):
            if _port_is_free(port):
                return port
        return 8765


def _http_get(url: str, timeout_s: float = 5.0) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        code = int(getattr(resp, "status", 200))
        headers = {k: v for k, v in resp.headers.items()}
        body = resp.read()
        return code, headers, body


def _pick_python_executable() -> str:
    # In some dev environments, `sys.executable` can be a launcher that isn't Python.
    base = os.path.basename(sys.executable).lower()
    if base.startswith("python"):
        return sys.executable
    for cand in ("python3", "python"):
        p = shutil.which(cand)
        if p:
            return p
    return sys.executable


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument(
        "--count", type=int, default=3, help="How many screenshots to attempt"
    )
    p.add_argument(
        "--out-dir",
        default="screenshot_test_out",
        help="Directory to write PNGs into",
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )
    log = logging.getLogger("test_screenshot_bridge")

    root = Path(__file__).resolve().parents[1]
    bridge_py = root / "phantom_backend" / "host_bridge.py"
    if not bridge_py.exists():
        log.error("Missing %s", bridge_py)
        return 2

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    port = _pick_free_port()
    url = f"http://127.0.0.1:{port}"

    log_path = out_dir / "bridge.log"
    log_f = log_path.open("wb")
    py = _pick_python_executable()
    proc = subprocess.Popen(
        [py, str(bridge_py), "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        env={**os.environ},
    )
    try:
        # Wait for /ping
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                code, _, body = _http_get(f"{url}/ping", timeout_s=1.0)
                if code == 200 and body.strip() == b"ok":
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            log.error("Bridge did not start")
            log.error("Bridge log: %s", log_path)
            return 1

        code, _, body = _http_get(f"{url}/status", timeout_s=2.0)
        if code == 200:
            log.info("bridge /status: %s", json.loads(body.decode("utf-8")))

        for i in range(int(args.count)):
            code, headers, body = _http_get(f"{url}/screenshot", timeout_s=20.0)
            method = headers.get("X-Phantom-Capture-Method", "unknown")
            size = len(body)
            log.info(
                "[%d/%d] code=%d method=%s bytes=%d",
                i + 1,
                args.count,
                code,
                method,
                size,
            )
            if code != 200:
                continue
            fp = out_dir / f"screenshot_{i + 1}_{method}_{size}b.png"
            fp.write_bytes(body)
            # Refresh status each time
            try:
                code2, _, body2 = _http_get(f"{url}/status", timeout_s=2.0)
                if code2 == 200:
                    log.info("status: %s", json.loads(body2.decode("utf-8")))
            except Exception:
                pass

        log.info("Wrote files to: %s", out_dir)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
        with contextlib.suppress(Exception):
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())
