from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from phantom_backend.games.registry import GameRegistry
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets
from phantom_backend.services.players import PlayerService


def _base_url() -> str:
    host = os.getenv("PHANTOM_HOST", "127.0.0.1")
    port = os.getenv("PHANTOM_PORT", "8000")
    return f"http://{host}:{port}"


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, resp.read().decode(errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")


def _http_post(url: str, payload: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode(errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")


def _print_jsonish(body: str) -> None:
    body = body.strip()
    if not body:
        return
    with contextlib.suppress(Exception):
        json.loads(body)


def _fetch_cheats(base: str, game: str) -> list[str]:
    status, body = _http_get(f"{base}/{game}/cheats")
    if status != 200:
        raise RuntimeError(f"Failed to fetch cheats: HTTP {status} {body}")
    obj = json.loads(body)
    cheats = obj.get("cheats", [])
    names: list[str] = []
    for c in cheats:
        n = c.get("name") if isinstance(c, dict) else None
        if n:
            names.append(str(n))
    return names


def _pick_cheat_name(base: str, game: str) -> str:
    """Let user type a cheat name; supports case-insensitive + partial matches."""
    names = _fetch_cheats(base, game)
    if not names:
        raise RuntimeError("No cheats returned by backend")

    for _i, _ in enumerate(names, 1):
        pass

    raw = _prompt("Cheat name (or number): ")
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(names):
            return names[idx - 1]

    q = raw.strip()
    if not q:
        return names[0]

    # Exact (case-insensitive)
    for n in names:
        if n.lower() == q.lower():
            return n

    # Partial
    matches = [n for n in names if q.lower() in n.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        for _i, _ in enumerate(matches, 1):
            pass
        pick = _prompt("Choose number: ")
        if pick.isdigit():
            idx = int(pick)
            if 1 <= idx <= len(matches):
                return matches[idx - 1]

    # Fall back: allow raw value (backend will error clearly)
    return q


def _prompt(prompt: str) -> str:
    return input(prompt).strip()


def _choose_game() -> str:
    while True:
        choice = _prompt("> ")
        if choice == "1":
            return "eldenring"
        if choice == "2":
            return "ds3"
        if choice == "0":
            raise SystemExit(0)


def _menu(game: str) -> None:
    base = _base_url()

    def _read_equipped_aow_eldenring_best_effort() -> None:
        """Best-effort: show equipped weapon IDs and possible AoW values from inventory entries.

        Notes:
        - Elden's player struct exposes weapon IDs, but not the AoW directly.
        - If you have multiple copies of the same weapon in inventory, AoW is ambiguous unless we can
          resolve which inventory entry is equipped.
        """
        reg = GameRegistry()
        adapter = reg.get("eldenring")
        mem = adapter.make_memory()
        try:
            resolver = adapter.make_resolver(mem)
            svc = PlayerService(mem=mem, resolver=resolver, game_key="eldenring")
            p0 = svc.get_player(0)
            eq = p0.equipment or {}

            # Read inventory list pointer.
            cfg = load_manager_offsets("eldenring")
            WEAPON = get_hex_int(cfg, "item_types", "WEAPON")
            player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")
            equip_inv_off = get_hex_int(cfg, "equipment", "equip_inventory_data")

            gdm_ptr_addr = resolver.resolve("GameDataManPtrAddr").address
            gdm = mem.read_ptr(gdm_ptr_addr)
            if not gdm:
                return

            player_game_data = mem.read_ptr(gdm + player_game_data_off)
            if not player_game_data:
                return

            equip_inventory_data = mem.read_ptr(player_game_data + equip_inv_off)
            if not equip_inventory_data:
                return

            inventory_list = mem.read_ptr(equip_inventory_data + 0x10)  # manager layout
            if not inventory_list:
                return

            inv_entry_size = 0x18
            inv_id_off = 0x04

            # Best-effort gem/AoW locations within a 0x18 entry (varies by version)
            gem_offsets = (0x0C, 0x10, 0x14)
            tail_data_idx = 0
            try:
                tail_data_idx = mem.read_i32(equip_inventory_data + 0x1C)
            except Exception:
                tail_data_idx = 0

            def _read_entry_dwords(entry_addr: int) -> list[int]:
                out: list[int] = []
                for off in range(0, inv_entry_size, 4):
                    try:
                        out.append(mem.read_i32(entry_addr + off) & 0xFFFFFFFF)
                    except Exception:
                        out.append(0xDEADDEAD)
                return out

            def _find_aow_candidates_for_weapon(
                base_weapon_id: int,
            ) -> dict[int, dict[str, object]]:
                """Return per-inventory-index info for entries matching the weapon id.

                Shape:
                  { idx: {
                      "gems": [..],
                      "entry": [dword0..dword5],
                      "final_idx": int,
                      "final_entry": [dword0..dword5],
                    } }
                """
                full = WEAPON | (base_weapon_id & 0x0FFFFFFF)
                out: dict[int, dict[str, object]] = {}
                want = full & 0xFFFFFFFF
                for i in range(2688):
                    entry = inventory_list + i * inv_entry_size
                    cur = mem.read_i32(entry + inv_id_off)
                    if cur != -1:
                        cur &= 0xFFFFFFFF
                    if (cur & 0xFFFFFFFF) != want:
                        continue

                    gems: list[int] = []
                    for off in gem_offsets:
                        try:
                            g = mem.read_i32(entry + off) & 0x0FFFFFFF
                            if g not in gems:
                                gems.append(g)
                        except Exception:
                            pass

                    # Try to find the AoW id nearby in a few common encodings, if user provides one.
                    # In FromSoft data, many IDs appear with "type bits" in high nibble (e.g. OTHER|id).
                    aow_hits: dict[str, list[int]] = {}
                    if expected_aow_id is not None:
                        try:
                            blob = mem.read_bytes(entry, 0x400)
                            base = int(expected_aow_id) & 0x0FFFFFFF
                            needles: list[tuple[str, bytes]] = [
                                (
                                    "aow_u32",
                                    int(expected_aow_id & 0xFFFFFFFF).to_bytes(
                                        4, "little", signed=False
                                    ),
                                ),
                                (
                                    "aow_u16",
                                    int(base & 0xFFFF).to_bytes(
                                        2, "little", signed=False
                                    ),
                                ),
                                (
                                    "OTHER|aow_u32",
                                    int((0x80000000 | base) & 0xFFFFFFFF).to_bytes(
                                        4, "little", signed=False
                                    ),
                                ),
                                (
                                    "GOODS|aow_u32",
                                    int((0x40000000 | base) & 0xFFFFFFFF).to_bytes(
                                        4, "little", signed=False
                                    ),
                                ),
                            ]

                            for label, needle in needles:
                                offsets: list[int] = []
                                start = 0
                                while True:
                                    j = blob.find(needle, start)
                                    if j < 0:
                                        break
                                    offsets.append(j)
                                    start = j + 1
                                if offsets:
                                    aow_hits[label] = offsets
                        except Exception:
                            pass

                    final_i = i + max(0, int(tail_data_idx))
                    final_entry = inventory_list + final_i * inv_entry_size
                    out[i] = {
                        "gems": gems,
                        "entry": _read_entry_dwords(entry),
                        "final_idx": final_i,
                        "final_entry": _read_entry_dwords(final_entry),
                        "aow_hits": aow_hits,
                    }
                return out

            weapon_keys = [
                "primary_left_wep",
                "primary_right_wep",
                "secondary_left_wep",
                "secondary_right_wep",
                "tertiary_left_wep",
                "tertiary_right_wep",
            ]

            expected_aow_id: int | None = None
            try:
                raw = _prompt(
                    "Optional: expected AoW id to search for (e.g. 20500), Enter to skip: "
                )
                if raw:
                    expected_aow_id = int(raw)
            except Exception:
                expected_aow_id = None

            if expected_aow_id is not None:
                pass

            # Show the equip_game_data "AoW/affinity internal" candidate field we discovered via watcher.
            # This value changes when you change AoW even if weapon_id stays the same.
            try:
                egd = player_game_data + 0x2B0
                mem.read_u32(egd + 0x0E8) & 0xFFFFFFFF
                mem.read_u32(egd + 0x0EC) & 0xFFFFFFFF
                mem.read_u32(egd + 0x01DC) & 0xFFFFFFFF
                mem.read_u32(egd + 0x01D0) & 0xFFFFFFFF
            except Exception:
                pass
            for k in weapon_keys:
                wid = int(eq.get(k, -1))
                if wid in (-1, 0xFFFFFFFF, 0x0FFFFFFF, 268435455, 0):
                    continue

                matches = _find_aow_candidates_for_weapon(wid)
                if not matches:
                    continue

                # Summarize candidates across entries
                all_gems: list[int] = []
                for info in matches.values():
                    gems = info.get("gems") if isinstance(info, dict) else []
                    for g in list(gems or []):
                        if g not in all_gems:
                            all_gems.append(g)

                if len(matches) == 1 and len(all_gems) == 1:
                    only_idx = next(iter(matches.keys()))
                    only = matches.get(only_idx, {})
                    only.get("final_idx")
                else:
                    # Ambiguous: multiple inventory entries and/or multiple gem offsets yield different values.
                    ", ".join(str(i) for i in list(matches.keys())[:6])
                    "" if len(matches) <= 6 else f" (+{len(matches) - 6} more)"

                # Debug-dump the first few matching entries so we can identify where AoW actually lives.
                for inv_idx in list(matches.keys())[:3]:
                    info = matches.get(inv_idx) or {}
                    info.get("entry")
                    info.get("final_idx")
                    info.get("final_entry")
                    info.get("aow_hits")
                    if expected_aow_id is not None:
                        pass
        finally:
            mem.close()

    while True:
        if game == "eldenring":
            pass

        choice = _prompt("> ")

        if choice == "1":
            url = f"{base}/admin/signatures/validate?{urllib.parse.urlencode({'game': game})}"
            status, body = _http_post(url)
            _print_jsonish(body)
            continue

        if choice == "2":
            status, body = _http_get(f"{base}/{game}/players")
            _print_jsonish(body)
            continue

        if choice == "3":
            pn = _prompt("player_num (0-5): ")
            status, body = _http_get(f"{base}/{game}/players/{pn}")
            _print_jsonish(body)
            continue

        if choice == "4":
            name = _pick_cheat_name(base, game)
            status, body = _http_post(
                f"{base}/{game}/cheats/{urllib.parse.quote(name)}/enable"
            )
            _print_jsonish(body)
            continue

        if choice == "5":
            name = _pick_cheat_name(base, game)
            status, body = _http_post(
                f"{base}/{game}/cheats/{urllib.parse.quote(name)}/disable"
            )
            _print_jsonish(body)
            continue

        if choice == "6":
            anim = _prompt("animation_id (default 60060): ") or "60060"
            status, body = _http_post(
                f"{base}/{game}/actions/fogwall?animation_id={urllib.parse.quote(anim)}"
            )
            _print_jsonish(body)
            continue

        if choice == "7":
            status, body = _http_post(f"{base}/{game}/actions/request_save")
            _print_jsonish(body)
            continue

        if choice == "8":
            confirm = _prompt("This will quit to menu. Type YES to continue: ")
            if confirm != "YES":
                continue
            status, body = _http_post(f"{base}/{game}/actions/quit_to_menu")
            _print_jsonish(body)
            continue

        if choice == "9":
            return

        if choice == "10" and game == "eldenring":
            with contextlib.suppress(Exception):
                _read_equipped_aow_eldenring_best_effort()
            continue

        if choice == "11":
            try:
                # Ask for specific stats based on game
                updates: dict[str, int | dict[str, int]] = {}

                if game == "eldenring":
                    r_str = _prompt("Runes (leave empty to skip): ")
                    if r_str:
                        updates["runes"] = int(r_str)

                    sb_str = _prompt("Scadutree Blessing (leave empty to skip): ")
                    rsa_str = _prompt(
                        "Revered Spirit Ash Blessing (leave empty to skip): "
                    )

                    if sb_str or rsa_str:
                        sote: dict[str, int] = {}
                        if sb_str:
                            sote["scadutree_blessing"] = int(sb_str)
                        if rsa_str:
                            sote["revered_spirit_ash_blessing"] = int(rsa_str)
                        updates["shadow_of_erdtree"] = sote

                elif game == "ds3":
                    s_str = _prompt("Souls (leave empty to skip): ")
                    if s_str:
                        updates["souls"] = int(s_str)

                if not updates:
                    continue

                pn = _prompt("player_num (default 0): ") or "0"
                status, body = _http_post(
                    f"{base}/{game}/players/{pn}/stats", {"stats": updates}
                )
                _print_jsonish(body)

            except Exception:
                pass
            continue

        if choice == "0":
            raise SystemExit(0)


def main() -> None:
    while True:
        game = _choose_game()
        _menu(game)


if __name__ == "__main__":
    main()
