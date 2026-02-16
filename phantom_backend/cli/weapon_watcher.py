from __future__ import annotations

import argparse
import struct
import time
from dataclasses import dataclass

from phantom_backend.core.errors import PhantomError
from phantom_backend.games.registry import GameRegistry
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets
from phantom_backend.services.players import PlayerService


@dataclass(frozen=True)
class _Region:
    name: str
    addr: int
    size: int


def _u32(b: bytes) -> int:
    return struct.unpack("<I", b)[0]


def _i32(b: bytes) -> int:
    return struct.unpack("<i", b)[0]


def _hex(addr: int) -> str:
    return hex(addr) if addr else "0x0"


def _diff_bytes(prev: bytes, cur: bytes, *, max_lines: int = 40) -> list[str]:
    """Return a human-readable diff of changed 4-byte aligned words."""
    out: list[str] = []
    n = min(len(prev), len(cur))
    # 4-byte stride so we can show u32/i32 and also 2-byte view.
    for off in range(0, n - (n % 4), 4):
        if prev[off : off + 4] == cur[off : off + 4]:
            continue
        pb = prev[off : off + 4]
        cb = cur[off : off + 4]
        out.append(
            f"+0x{off:04X}: {pb.hex()} -> {cb.hex()}  "
            f"u32 {(_u32(pb))} -> {(_u32(cb))}  "
            f"i32 {(_i32(pb))} -> {(_i32(cb))}"
        )
        if len(out) >= max_lines:
            out.append(f"... truncated ({len(out)}+ changes)")
            break
    return out


def _read_region(mem, addr: int, size: int) -> bytes:
    try:
        return mem.read_bytes(addr, size)
    except Exception:
        return b""


def _resolve_regions(game_key: str, player_num: int):
    reg = GameRegistry()
    adapter = reg.get(game_key)
    mem = adapter.make_memory()
    resolver = adapter.make_resolver(mem)

    # Use PlayerService for the stable "equipped weapon ids" view.
    psvc = PlayerService(mem=mem, resolver=resolver, game_key=game_key)

    cfg = load_manager_offsets(game_key)
    player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")

    gdm_ptr_addr = resolver.resolve("GameDataManPtrAddr").address
    gdm = mem.read_ptr(gdm_ptr_addr)
    player_game_data = mem.read_ptr(gdm + player_game_data_off) if gdm else 0

    regions: list[_Region] = []

    # Region 1: EquipGameData (manager uses +0x2B0). This often contains currently equipped ids/slots.
    if player_game_data:
        regions.append(
            _Region(name="equip_game_data", addr=player_game_data + 0x2B0, size=0x800)
        )

    # Region 2: Player "Ins" region (from common CE scripts): WorldChrMan+0x1E508 -> ptr.
    # This tends to change when weapon arts / states change, even if we don't know exact offsets yet.
    try:
        wcm_ptr_addr = resolver.resolve("WorldChrManPtrAddr").address
        wcm = mem.read_ptr(wcm_ptr_addr)
        ins = mem.read_ptr(wcm + 0x1E508) if wcm else 0
        if ins:
            regions.append(_Region(name="player_ins", addr=ins, size=0x2000))
    except Exception:
        pass

    return mem, resolver, psvc, regions


def _print_equipped_weapons(psvc: PlayerService, player_num: int) -> None:
    psvc.get_player(player_num)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Watch for weapon/AoW/affinity-related memory changes."
    )
    ap.add_argument(
        "--game", default="eldenring", choices=["eldenring"], help="Game key"
    )
    ap.add_argument("--player", type=int, default=0, help="Player slot (0=local)")
    ap.add_argument(
        "--interval", type=float, default=0.5, help="Polling interval in seconds"
    )
    ap.add_argument(
        "--watch-ins",
        action="store_true",
        help="Also watch PlayerIns memory (very noisy; changes constantly even without AoW edits).",
    )
    ap.add_argument(
        "--max-lines",
        type=int,
        default=40,
        help="Max changed offsets to print per region per tick",
    )
    ap.add_argument(
        "--focus-equip-fields",
        action="store_true",
        help="Only print changes for a small set of equip_game_data fields (low-noise, best for finding AoW).",
    )
    args = ap.parse_args(argv)

    mem, _resolver, psvc, regions = _resolve_regions(args.game, args.player)
    try:
        if not regions:
            raise PhantomError(
                "No regions could be resolved to watch (is the game running?)"
            )

        # PlayerIns is very noisy; default behavior is to watch only equip_game_data unless explicitly requested.
        if not args.watch_ins:
            regions = [r for r in regions if r.name != "player_ins"]

        prev_regions: dict[str, bytes] = {}
        prev_equipped: dict[str, int | None] | None = None
        prev_equip_fields: dict[int, int] | None = None
        tick = 0
        while True:
            tick += 1
            # Compute equipped IDs snapshot (cheap) and region diffs (heavier).
            p = psvc.get_player(args.player)
            eq = p.equipment or {}
            keys = [
                "primary_left_wep",
                "primary_right_wep",
                "secondary_left_wep",
                "secondary_right_wep",
                "tertiary_left_wep",
                "tertiary_right_wep",
                "primary_arrow",
                "primary_bolt",
                "secondary_arrow",
                "secondary_bolt",
                "tertiary_arrow",
                "tertiary_bolt",
            ]
            equipped_now: dict[str, int | None] = {k: eq.get(k) for k in keys}
            equipped_changed = (
                prev_equipped is not None and equipped_now != prev_equipped
            )

            any_region_changed = False
            region_change_lines: list[str] = []

            # Optional: focus mode for equip_game_data: track a few offsets that are relevant for AoW discovery.
            # Offsets observed from real runs:
            # - 0x00E8 and 0x0348: weapon id changes
            # - 0x01DC: small integer that changes when you tweak AoW/affinity (candidate AoW-internal id)
            # - 0x01D0 / 0x06B4: other related counters/ids
            equip_field_offsets = (0x00E8, 0x0348, 0x01DC, 0x01D0, 0x06B4)
            equip_fields_now: dict[int, int] = {}
            equip_base = next(
                (r.addr for r in regions if r.name == "equip_game_data"), 0
            )
            if equip_base:
                for off in equip_field_offsets:
                    try:
                        equip_fields_now[off] = mem.read_u32(equip_base + off)  # type: ignore[attr-defined]
                    except Exception:
                        try:
                            equip_fields_now[off] = mem.read_u32(equip_base + off)  # pyright: ignore
                        except Exception:
                            equip_fields_now[off] = 0xDEADDEAD

            equip_fields_changed = (
                prev_equip_fields is not None and equip_fields_now != prev_equip_fields
            )
            for r in regions:
                cur = _read_region(mem, r.addr, r.size)
                prev = prev_regions.get(r.name)
                if prev is None:
                    prev_regions[r.name] = cur
                    # Baseline capture is noisy; do it silently.
                    continue
                if not prev or not cur:
                    any_region_changed = True
                    region_change_lines.append(
                        f"[{r.name}] unreadable (prev={len(prev) if prev else 0}, cur={len(cur) if cur else 0})"
                    )
                    prev_regions[r.name] = cur
                    continue

                # In focus mode, only report equip_game_data field deltas (no big diffs).
                if args.focus_equip_fields and r.name == "equip_game_data":
                    # handled below via equip_fields
                    prev_regions[r.name] = cur
                    continue

                changes = _diff_bytes(prev, cur, max_lines=args.max_lines)
                if changes:
                    any_region_changed = True
                    region_change_lines.append(
                        f"[{r.name}] {len(changes)} word changes:"
                    )
                    region_change_lines.extend([f"  {line}" for line in changes])
                prev_regions[r.name] = cur

            # Only print when something changed.
            if prev_equipped is None:
                prev_equipped = equipped_now
                if equip_base:
                    prev_equip_fields = dict(equip_fields_now)
            elif (
                equipped_changed
                or any_region_changed
                or (args.focus_equip_fields and equip_fields_changed)
            ):
                if equipped_changed:
                    pass
                if args.focus_equip_fields and equip_base and equip_fields_changed:
                    # Print a compact field diff
                    assert prev_equip_fields is not None
                    for off in equip_field_offsets:
                        old = prev_equip_fields.get(off, 0)
                        new = equip_fields_now.get(off, 0)
                        if old != new:
                            pass
                    # Helpful signal: did AoW-like field change without weapon id change?
                    if prev_equip_fields.get(0x00E8) == equip_fields_now.get(
                        0x00E8
                    ) and prev_equip_fields.get(0x01DC) != equip_fields_now.get(0x01DC):
                        pass
                if region_change_lines:
                    for _line in region_change_lines:
                        pass
                prev_equipped = equipped_now
                if equip_base:
                    prev_equip_fields = dict(equip_fields_now)

            time.sleep(max(0.05, float(args.interval)))
    finally:
        mem.close()


if __name__ == "__main__":
    main()
