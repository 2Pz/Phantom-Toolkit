"""
Native Linux GUI wrapper for Phantom Toolkit (pywebview).

This is intentionally separate from the Windows/Proton process:
- The Windows build runs the FastAPI backend under Proton/Wine.
- This wrapper runs natively on Linux and embeds the UI URL in a native
  window using pywebview (GTK/WebKit backend), giving an "app window" feel
  without bundling a full browser engine.
"""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("--url", required=True, help="UI URL, e.g. http://127.0.0.1:8000")
    p.add_argument("--title", default="Phantom Toolkit")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    return p.parse_args(argv[1:])


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    args = _parse_args(argv)

    import os

    import webview

    icon_path = None
    if getattr(sys, "frozen", False):
        icon_path = os.path.join(sys._MEIPASS, "assets", "icon.ico")
    else:
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "icon.ico"
        )

    webview.create_window(
        str(args.title),
        str(args.url),
        width=int(args.width),
        height=int(args.height),
        resizable=True,
    )
    webview.start(
        debug=False, icon=icon_path if icon_path and os.path.exists(icon_path) else None
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
