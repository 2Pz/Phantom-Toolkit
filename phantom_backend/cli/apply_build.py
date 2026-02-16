from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _base_url() -> str:
    host = os.getenv("PHANTOM_HOST", "127.0.0.1")
    port = os.getenv("PHANTOM_PORT", "8000")
    return f"http://{host}:{port}"


def _http_post(url: str, payload: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode(errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")


def _infer_game(build: dict) -> str:
    if "shadow_of_erdtree" in build:
        return "eldenring"
    if "toolbelt_1" in (build.get("equipment") or {}):
        return "ds3"
    return "eldenring"


def main(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv[1:]
    if not argv:
        raise SystemExit(2)

    path = Path(argv[0])
    game = None
    player = 0
    i = 1
    while i < len(argv):
        if argv[i] == "--game" and i + 1 < len(argv):
            game = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--player" and i + 1 < len(argv):
            player = int(argv[i + 1])
            i += 2
            continue
        i += 1

    build = json.loads(path.read_text(encoding="utf-8"))
    if game is None:
        game = _infer_game(build)

    base = _base_url()
    # Validate signatures first
    vurl = f"{base}/admin/signatures/validate?{urllib.parse.urlencode({'game': game})}"
    code, body = _http_post(vurl, {})
    if code != 200:
        raise SystemExit(1)

    equipment = build.get("equipment") or {}
    stats = build.get("stats") or None
    sote = build.get("shadow_of_erdtree") or None

    payload = {"equipment": equipment}
    if stats:
        payload["stats"] = stats
    if sote:
        payload["shadow_of_erdtree"] = sote

    url = f"{base}/{game}/players/{player}/build"
    code, body = _http_post(url, payload)
    if code != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
