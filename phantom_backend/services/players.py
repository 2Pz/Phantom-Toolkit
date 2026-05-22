from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phantom_backend.core.errors import PhantomError
from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver
from phantom_backend.services.equip_apply import EquipApplyService
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets


@dataclass
class PlayerState:
    player_num: int
    is_valid: bool
    name: str = "Unknown"
    steam_id: str | None = None
    level: int = 0
    stats: dict[str, Any] | None = None
    equipment: dict[str, Any] | None = None


class PlayerService:
    """Read/write player state.

    Note: AOB-only. Requires base symbols to be present and resolvable.
    """

    # Shared idea: both ER and DS3 iterate 0..5. Keep game-specific pointer chains in adapters later.
    PLAYER_SLOTS = 6

    def __init__(self, *, mem: MemoryClient, resolver: SymbolResolver, game_key: str):
        self._mem = mem
        self._resolver = resolver
        self._game = game_key

    def _world_chr_man(self) -> int:
        # Convention: WorldChrManPtrAddr resolves to the address that contains the pointer.
        sym = self._resolver.resolve("WorldChrManPtrAddr")
        return self._mem.read_ptr(sym.address)

    def list_players(self) -> list[PlayerState]:
        players: list[PlayerState] = []
        for i in range(self.PLAYER_SLOTS):
            st = self.get_player(i)
            if st.is_valid:
                players.append(st)
        return players

    def get_player(self, player_num: int) -> PlayerState:
        if self._game == "eldenring":
            return self._get_player_eldenring(player_num)
        if self._game == "ds3":
            return self._get_player_ds3(player_num)
        raise PhantomError(f"Unsupported game: {self._game}")

    def write_stats(self, player_num: int, stats: dict[str, Any]) -> None:
        if player_num != 0:
            raise PhantomError("Writing is only supported for local player_num=0")
        if self._game == "eldenring":
            self._write_stats_eldenring(player_num, stats)
            return
        if self._game == "ds3":
            self._write_stats_ds3(player_num, stats)
            return
        raise PhantomError(f"Unsupported game: {self._game}")

    def write_build(self, player_num: int, equipment: dict[str, Any]) -> None:
        if player_num != 0:
            raise PhantomError("Writing is only supported for local player_num=0")
        if self._game == "eldenring":
            self._write_build_eldenring(player_num, equipment)
            return
        if self._game == "ds3":
            self._write_build_ds3(player_num, equipment)
            return
        raise PhantomError(f"Unsupported game: {self._game}")

    def _get_player_eldenring(self, player_num: int) -> PlayerState:
        # Based on internal player logic:
        # WorldChrMan -> 0x10EF8 -> *(...) -> *(... + player_num*0x10) -> *(... + 0x580) = base_addr
        st = PlayerState(player_num=player_num, is_valid=False, stats={}, equipment={})
        try:
            wcm = self._world_chr_man()
            addr = self._mem.read_ptr(wcm + 0x10EF8)
            addr = self._mem.read_ptr(addr + (player_num * 0x10))
            base_addr = self._mem.read_ptr(addr + 0x580)
            if not base_addr:
                return st

            level = self._mem.read_i32(base_addr + 0x68)
            max_hp = self._mem.read_i32(base_addr + 0x14)

            # Diagnostic for Linux investigation
            if self._game == "eldenring":
                name_addr = base_addr + 0x9C
                name_chars = []
                for j in range(32):
                    ch = self._mem.read_u16(name_addr + j * 2)
                    if ch == 0:
                        break
                    name_chars.append(ch)
                name = "".join(map(chr, name_chars))
                # print(f"DEBUG: Player {player_num} level={level} hp={max_hp} name={name}")

            if not (0 <= level <= 713) or max_hp <= 0:
                return st

            # Name UTF-16 (32 chars)
            name_chars: list[int] = []
            name_addr = base_addr + 0x9C
            for j in range(32):
                ch = self._mem.read_u16(name_addr + j * 2)
                if ch == 0:
                    break
                name_chars.append(ch)
            name = "".join(map(chr, name_chars)) if name_chars else "Unknown"

            # Valid so far. Let's get extra debug info from the 'addr' (PlayerIns)
            chr_type = self._mem.read_i32(addr + 0x68)
            team_type = self._mem.read_i32(addr + 0x6C)

            st.is_valid = True
            st.name = name
            st.level = level
            st.stats |= {
                "level": level,
                "chr_type": chr_type,
                "team_type": team_type,
                "hp": self._mem.read_i32(base_addr + 0x10),
                "max_hp": max_hp,
                "max_fp": self._mem.read_i32(base_addr + 0x20),
                "max_stamina": self._mem.read_i32(base_addr + 0x30),
                "vigor": self._mem.read_i32(base_addr + 0x3C),
                "mind": self._mem.read_i32(base_addr + 0x40),
                "endurance": self._mem.read_i32(base_addr + 0x44),
                "strength": self._mem.read_i32(base_addr + 0x48),
                "dexterity": self._mem.read_i32(base_addr + 0x4C),
                "intelligence": self._mem.read_i32(base_addr + 0x50),
                "faith": self._mem.read_i32(base_addr + 0x54),
                "arcane": self._mem.read_i32(base_addr + 0x58),
                "runes": self._mem.read_i32(base_addr + 0x6C),
                "scadutree_blessing": self._mem.read_u8(base_addr + 0xFC),
                "revered_spirit_ash_blessing": self._mem.read_u8(base_addr + 0xFD),
            }

            # Elden Ring Steam ID
            try:
                # Based on CE: [[[WorldChrMan]+10EF8]+player_offset]+5B0] + 8
                # Note: This offset may return 0 for the local player, but works for phantoms.
                sid_base = self._mem.read_ptr(addr + 0x5B0)
                if sid_base:
                    sid_val = self._mem.read_u64(sid_base + 0x8)
                    if sid_val > 0:
                        st.steam_id = str(sid_val)
            except Exception:
                pass

            # Equipment/build (IDs)
            st.equipment |= {
                "primary_left_wep": self._mem.read_i32(base_addr + 0x398),
                "primary_right_wep": self._mem.read_i32(base_addr + 0x39C),
                "secondary_left_wep": self._mem.read_i32(base_addr + 0x3A0),
                "secondary_right_wep": self._mem.read_i32(base_addr + 0x3A4),
                "tertiary_left_wep": self._mem.read_i32(base_addr + 0x3A8),
                "tertiary_right_wep": self._mem.read_i32(base_addr + 0x3AC),
                "primary_arrow": self._mem.read_i32(base_addr + 0x3B0),
                "primary_bolt": self._mem.read_i32(base_addr + 0x3B4),
                "secondary_arrow": self._mem.read_i32(base_addr + 0x3B8),
                "secondary_bolt": self._mem.read_i32(base_addr + 0x3BC),
                "tertiary_arrow": self._mem.read_i32(base_addr + 0x3C0),
                "tertiary_bolt": self._mem.read_i32(base_addr + 0x3C4),
                "helmet": self._mem.read_i32(base_addr + 0x3C8),
                "armor": self._mem.read_i32(base_addr + 0x3CC),
                "gauntlet": self._mem.read_i32(base_addr + 0x3D0),
                "leggings": self._mem.read_i32(base_addr + 0x3D4),
                "hair": self._mem.read_i32(base_addr + 0x3D8),
                "accessory_1": self._mem.read_i32(base_addr + 0x3DC),
                "accessory_2": self._mem.read_i32(base_addr + 0x3E0),
                "accessory_3": self._mem.read_i32(base_addr + 0x3E4),
                "accessory_4": self._mem.read_i32(base_addr + 0x3E8),
                "accessory_5": self._mem.read_i32(base_addr + 0x3EC),
            }

            # Magic slots (use offsets.toml when possible, fallback to known list)
            try:
                cfg = load_manager_offsets("eldenring")
                magic_base_off = get_hex_int(cfg, "equipment", "magic_slots_base")
                magic_base = self._mem.read_ptr(base_addr + magic_base_off)
                magic_slot_offsets = cfg.get("equipment", {}).get(
                    "magic_slot_offsets", {}
                )
                # keys are slot_0..slot_13 with hex strings
                for i in range(14):
                    key = f"slot_{i}"
                    off_val = magic_slot_offsets.get(key)
                    if off_val is None:
                        continue
                    off = int(str(off_val), 16)
                    mid = self._mem.read_u32(magic_base + off) & 0x0FFFFFFF
                    st.equipment[f"magic_slot_{i}"] = (
                        -1 if mid in (0x0FFFFFFF, 0xFFFFFFFF) else int(mid)
                    )
            except Exception:
                # fallback to the known offsets used in the old manager
                magic_base = self._mem.read_ptr(base_addr + 0x530)
                magic_offsets = [
                    0x10,
                    0x18,
                    0x20,
                    0x28,
                    0x30,
                    0x38,
                    0x40,
                    0x48,
                    0x50,
                    0x58,
                    0x60,
                    0x68,
                    0x70,
                    0x78,
                ]
                for i, off in enumerate(magic_offsets):
                    mid = self._mem.read_u32(magic_base + off) & 0x0FFFFFFF
                    st.equipment[f"magic_slot_{i}"] = (
                        -1 if mid in (0x0FFFFFFF, 0xFFFFFFFF) else int(mid)
                    )

            # Quick items (from GameDataMan + player_game_data + quick_item_offsets)
            try:
                cfg = load_manager_offsets("eldenring")
                player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")
                gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
                gdm = self._mem.read_ptr(gdm_ptr_addr)
                player_data = self._mem.read_ptr(gdm + player_game_data_off)

                # Wondrous Physick slots from EquipGameData (offset +0x2B0 from PlayerGameData)
                # Slot 1: +0x2B0 + 0x3E4 = +0x694
                # Slot 2: +0x2B0 + 0x3E8 = +0x698
                try:
                    addr1 = player_data + 0x694
                    p1 = self._mem.read_u32(addr1)
                    addr2 = player_data + 0x698
                    p2 = self._mem.read_u32(addr2)

                    st.equipment["physick_tear_1"] = (
                        int(p1 & 0x0FFFFFFF) if p1 != 0xFFFFFFFF else -1
                    )
                    st.equipment["physick_tear_2"] = (
                        int(p2 & 0x0FFFFFFF) if p2 != 0xFFFFFFFF else -1
                    )
                except Exception:
                    pass

                # Great Rune slot (PlayerGameData + 0x5C0)
                try:
                    gr_addr = player_data + 0x5C0
                    gr = self._mem.read_u32(gr_addr)
                    st.equipment["great_rune"] = int(gr & 0x0FFFFFFF) if gr != 0 else -1
                except Exception:
                    pass

                qio = cfg.get("equipment", {}).get("quick_item_offsets", {})
                for slot in range(1, 11):
                    key = f"slot_{slot}"
                    if key not in qio:
                        continue
                    off = int(str(qio[key]), 16)
                    qid = self._mem.read_u32(player_data + off) & 0x0FFFFFFF
                    st.equipment[f"quick_item_{slot}"] = int(qid)
                    st.equipment[f"quick_item_{slot}"] = int(qid)
            except Exception:
                pass

            return st
        except Exception:
            return st

    def _eld_base_addr(self, player_num: int) -> int:
        wcm = self._world_chr_man()
        addr = self._mem.read_ptr(wcm + 0x10EF8)
        addr = self._mem.read_ptr(addr + (player_num * 0x10))
        return self._mem.read_ptr(addr + 0x580)

    def _ds3_base_addr(self, player_num: int) -> int:
        wcm = self._world_chr_man()
        player_offsets = [0x0, 0x38, 0x70, 0xA8, 0xE0, 0x118]
        po = player_offsets[player_num] if player_num < len(player_offsets) else 0
        addr = self._mem.read_ptr(wcm + 0x40)
        addr = self._mem.read_ptr(addr + po)
        return self._mem.read_ptr(addr + 0x1FA0)

    def _write_stats_eldenring(self, player_num: int, stats: dict[str, Any]) -> None:
        base_addr = self._eld_base_addr(player_num)
        # Core stats
        int_fields = {
            "level": 0x68,
            "vigor": 0x3C,
            "mind": 0x40,
            "endurance": 0x44,
            "strength": 0x48,
            "dexterity": 0x4C,
            "intelligence": 0x50,
            "faith": 0x54,
            "arcane": 0x58,
            "runes": 0x6C,
            "health": 0x10,
            "max_hp": 0x14,
            "max_fp": 0x20,
            "max_stamina": 0x30,
        }
        # Normalize keys to lowercase for case-insensitive matching
        stats_lower = {k.lower(): v for k, v in stats.items()}

        for k, off in int_fields.items():
            if k in stats_lower and isinstance(stats_lower[k], (int, float)):
                val = int(stats_lower[k])
                # Defensive clamping: level and attributes should be >= 1, others >= 0
                if k in (
                    "vigor",
                    "mind",
                    "endurance",
                    "strength",
                    "dexterity",
                    "intelligence",
                    "faith",
                    "arcane",
                ):
                    val = min(99, max(1, val))
                elif k == "level":
                    val = max(1, val)
                else:
                    val = max(0, val)

                # Runes/Health can be large, use u32 to avoid overflow if they exceed 2.1B
                self._mem.write_u32(base_addr + off, val & 0xFFFFFFFF)

        # Blessings (Shadow of the Erdtree)
        sote = (
            stats.get("shadow_of_erdtree")
            if isinstance(stats.get("shadow_of_erdtree"), dict)
            else None
        )
        if sote:
            if "scadutree_blessing" in sote:
                val = max(0, int(sote["scadutree_blessing"]))
                self._mem.write_u8(base_addr + 0xFC, val)
            if "revered_spirit_ash_blessing" in sote:
                val = max(0, int(sote["revered_spirit_ash_blessing"]))
                self._mem.write_u8(base_addr + 0xFD, val)

    def _write_stats_ds3(self, player_num: int, stats: dict[str, Any]) -> None:
        base_addr = self._ds3_base_addr(player_num)
        int_fields = {
            "level": 0x70,
            "vigor": 0x44,
            "attunement": 0x48,
            "endurance": 0x4C,
            "vitality": 0x6C,
            "strength": 0x50,
            "dexterity": 0x54,
            "intelligence": 0x58,
            "faith": 0x5C,
            "luck": 0x60,
            "souls": 0x74,
            "health": 0x18,
            "max_hp": 0x1C,
            "max_fp": 0x2C,
            "max_stamina": 0x3C,
        }
        # Normalize keys to lowercase for case-insensitive matching
        stats_lower = {k.lower(): v for k, v in stats.items()}

        for k, off in int_fields.items():
            if k in stats_lower and isinstance(stats_lower[k], (int, float)):
                val = int(stats_lower[k])
                # Defensive clamping: level and attributes should be >= 1, others >= 0
                if k in (
                    "vigor",
                    "attunement",
                    "endurance",
                    "vitality",
                    "strength",
                    "dexterity",
                    "intelligence",
                    "faith",
                    "luck",
                ):
                    val = min(99, max(1, val))
                elif k == "level":
                    val = max(1, val)
                else:
                    val = max(0, val)

                # Souls/Health can be large, use u32 to avoid overflow if they exceed 2.1B
                self._mem.write_u32(base_addr + off, val & 0xFFFFFFFF)

    def _write_build_eldenring(
        self, player_num: int, equipment: dict[str, Any]
    ) -> None:
        base_addr = self._eld_base_addr(player_num)

        # Normalize weapon dicts like {"id": X, "ash_of_war": Y} -> id (we do not apply AoW in this write path).
        def norm(v: Any) -> int:
            if isinstance(v, dict) and "id" in v:
                return int(v["id"])
            return int(v)

        # Magic slots: preserve high bits, replace low 28 bits
        cfg = load_manager_offsets("eldenring")
        magic_base_off = get_hex_int(cfg, "equipment", "magic_slots_base")
        magic_base = self._mem.read_ptr(base_addr + magic_base_off)
        magic_slot_offsets = cfg.get("equipment", {}).get("magic_slot_offsets", {})
        for i in range(14):
            slot_key = f"magic_slot_{i}"
            if slot_key not in equipment:
                continue
            off_val = magic_slot_offsets.get(f"slot_{i}")
            if off_val is None:
                continue
            off = int(str(off_val), 16)
            cur = self._mem.read_u32(magic_base + off)
            want = norm(equipment[slot_key])
            low = (
                0x0FFFFFFF
                if want in (-1, 0x0FFFFFFF, 0xFFFFFFFF)
                else (want & 0x0FFFFFFF)
            )
            newv = (cur & 0xF0000000) | low
            self._mem.write_u32(magic_base + off, newv)

        # Quick items: preserve high bits where possible; default to GOODS if empty
        player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")
        gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
        gdm = self._mem.read_ptr(gdm_ptr_addr)
        player_data = self._mem.read_ptr(gdm + player_game_data_off)
        qio = cfg.get("equipment", {}).get("quick_item_offsets", {})
        goods_type = get_hex_int(cfg, "item_types", "GOODS")
        for slot in range(1, 11):
            key = f"quick_item_{slot}"
            if key not in equipment:
                continue
            off_val = qio.get(f"slot_{slot}")
            if off_val is None:
                continue
            off = int(str(off_val), 16)
            cur = self._mem.read_u32(player_data + off)
            want = norm(equipment[key])
            low = want & 0x0FFFFFFF
            if want in (-1, 0xFFFFFFFF, 0x0FFFFFFF, 268435455):
                self._mem.write_u32(player_data + off, 0x0FFFFFFF)
            else:
                high = cur & 0xF0000000
                if high == 0:
                    high = goods_type
                self._mem.write_u32(player_data + off, high | low)

        # Finally, perform a real "equip" pass (give missing items + call equip funcs) using AOB-only symbols.
        # This matches the managers' behavior and is required for "fully equipped" builds.
        EquipApplyService(
            mem=self._mem, resolver=self._resolver, game_key="eldenring"
        ).apply_build(player_num=player_num, equipment=equipment)

    def _write_build_ds3(self, player_num: int, equipment: dict[str, Any]) -> None:
        base_addr = self._ds3_base_addr(player_num)

        def norm(v: Any) -> int:
            if isinstance(v, dict) and "id" in v:
                return int(v["id"])
            return int(v)

        # Resolve GameDataMan -> game_data pointer (as in DS3 manager)
        gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
        gdm = self._mem.read_ptr(gdm_ptr_addr)
        game_data = self._mem.read_ptr(gdm + 0x10) if gdm else 0

        # Base equipment
        eq_offsets = {
            "primary_left_wep": 0x32C,
            "primary_right_wep": 0x330,
            "secondary_left_wep": 0x334,
            "secondary_right_wep": 0x338,
            "tertiary_left_wep": 0x33C,
            "tertiary_right_wep": 0x340,
            "helmet": 0x35C,
            "armor": 0x360,
            "gauntlet": 0x364,
            "leggings": 0x368,
            "ring_1": 0x370,
            "ring_2": 0x374,
            "ring_3": 0x378,
            "ring_4": 0x37C,
            "accessory_1": 0x370,
            "accessory_2": 0x374,
            "accessory_3": 0x378,
            "accessory_4": 0x37C,
            "covenant": 0x380,
        }
        for k, off in eq_offsets.items():
            if k in equipment:
                self._mem.write_u32(base_addr + off, norm(equipment[k]) & 0xFFFFFFFF)

        # Ammo/quick/toolbelt/spells
        if game_data:
            ammo = {
                "primary_arrow": 0x344,
                "primary_bolt": 0x348,
                "secondary_arrow": 0x34C,
                "secondary_bolt": 0x350,
            }
            for k, off in ammo.items():
                if k in equipment:
                    # DS3 IDs also benefit from u32 to avoid overflow with flags
                    self._mem.write_u32(
                        game_data + off, norm(equipment[k]) & 0xFFFFFFFF
                    )

            quick_item_offsets = {
                1: 0x5AC,
                2: 0x5B0,
                3: 0x5B4,
                4: 0x5B8,
                5: 0x5BC,
                6: 0x5C0,
                7: 0x5C4,
                8: 0x5C8,
                9: 0x5CC,
                10: 0x5D0,
            }
            toolbelt_offsets = {1: 0x5D4, 2: 0x5D8, 3: 0x5DC, 4: 0x5E0, 5: 0x5E4}
            for slot, off in quick_item_offsets.items():
                key = f"quick_item_{slot}"
                if key in equipment:
                    self._mem.write_u32(
                        game_data + off, norm(equipment[key]) & 0x0FFFFFFF
                    )
            for slot, off in toolbelt_offsets.items():
                key = f"toolbelt_{slot}"
                if key in equipment:
                    self._mem.write_u32(
                        game_data + off, norm(equipment[key]) & 0x0FFFFFFF
                    )

            # Spells
            try:
                spell_base = self._mem.read_ptr(game_data + 0x470)
                spell_offsets = [
                    0x18,
                    0x20,
                    0x28,
                    0x30,
                    0x38,
                    0x40,
                    0x48,
                    0x50,
                    0x58,
                    0x60,
                    0x68,
                    0x70,
                    0x78,
                    0x80,
                ]
                for i, off in enumerate(spell_offsets):
                    key = f"magic_slot_{i}"
                    if key in equipment:
                        want = norm(equipment[key])
                        low = (
                            0x0FFFFFFF
                            if want in (-1, 0xFFFFFFFF, 0x0FFFFFFF)
                            else (want & 0x0FFFFFFF)
                        )
                        cur = self._mem.read_u32(spell_base + off)
                        self._mem.write_u32(spell_base + off, (cur & 0xF0000000) | low)
            except Exception:
                pass

        # Finally, perform a real "equip" pass (give missing items + call equip funcs) using AOB-only symbols.
        # This matches the DS3 manager's behavior and is required for "fully equipped" builds.
        EquipApplyService(
            mem=self._mem, resolver=self._resolver, game_key="ds3"
        ).apply_build(player_num=player_num, equipment=equipment)

    def _get_player_ds3(self, player_num: int) -> PlayerState:
        # Based on internal player logic:
        # offsets table: [0x0,0x38,0x70,0xA8,0xE0,0x118]
        st = PlayerState(player_num=player_num, is_valid=False, stats={}, equipment={})
        try:
            base_addr = self._ds3_base_addr(player_num)

            level = self._mem.read_i32(base_addr + 0x70)
            if not (1 <= level <= 802):
                return st

            # Name UTF-16 (32 chars)
            name_chars: list[int] = []
            name_addr = base_addr + 0x88
            for j in range(32):
                ch = self._mem.read_u16(name_addr + j * 2)
                if ch == 0:
                    break
                name_chars.append(ch)
            name = "".join(map(chr, name_chars)) if name_chars else "Unknown"

            # Steam ID (offset 0x7D8) - Try multiple approaches matching DS3 logic
            steam_id = None
            try:
                sid_addr = base_addr + 0x7D8

                # Approach 1: Read as wide string (UTF-16)
                try:
                    name_chars_sid: list[int] = []
                    for k in range(32):
                        ch_sid = self._mem.read_u16(sid_addr + k * 2)
                        if ch_sid == 0:
                            break
                        name_chars_sid.append(ch_sid)
                    if name_chars_sid:
                        candidate = "".join(map(chr, name_chars_sid))
                        # Check if it's a hex steam ID (16 chars, usually starts with 0110 for valid players or similar)
                        if len(candidate) == 16:
                            try:
                                steam_id = str(int(candidate, 16))
                            except ValueError:
                                steam_id = candidate
                        elif len(candidate) > 5:
                            steam_id = candidate
                except Exception:
                    pass

                # Approach 2: Read as ASCII string
                if not steam_id:
                    try:
                        ascii_chars: list[int] = []
                        for k in range(32):
                            ch_ascii = self._mem.read_u8(sid_addr + k)
                            if ch_ascii == 0:
                                break
                            ascii_chars.append(ch_ascii)
                        if ascii_chars:
                            candidate = "".join(map(chr, ascii_chars))
                            if len(candidate) == 16:
                                try:
                                    steam_id = str(int(candidate, 16))
                                except ValueError:
                                    steam_id = candidate
                            elif len(candidate) > 5:
                                steam_id = candidate
                    except Exception:
                        pass

                # Approach 3: Read as numeric value (int64)
                if not steam_id:
                    try:
                        sid_val = self._mem.read_u64(sid_addr)
                        if sid_val > 0:
                            steam_id = str(sid_val)
                    except Exception:
                        pass

            except Exception:
                pass

            st.is_valid = True
            st.name = name
            st.steam_id = steam_id
            st.level = level
            st.stats |= {
                "level": level,
                "hp": self._mem.read_i32(base_addr + 0x18),
                "max_hp": self._mem.read_i32(base_addr + 0x1C),
                "max_fp": self._mem.read_i32(base_addr + 0x2C),
                "max_stamina": self._mem.read_i32(base_addr + 0x3C),
                "vigor": self._mem.read_i32(base_addr + 0x44),
                "attunement": self._mem.read_i32(base_addr + 0x48),
                "endurance": self._mem.read_i32(base_addr + 0x4C),
                "strength": self._mem.read_i32(base_addr + 0x50),
                "dexterity": self._mem.read_i32(base_addr + 0x54),
                "intelligence": self._mem.read_i32(base_addr + 0x58),
                "faith": self._mem.read_i32(base_addr + 0x5C),
                "luck": self._mem.read_i32(base_addr + 0x60),
                "souls": self._mem.read_i32(base_addr + 0x74),
                "vitality": self._mem.read_i32(base_addr + 0x6C),
            }

            # Equipment/build (IDs) based on internal player logic
            # Uses game_data = *(GameDataMan + 0x10) for ammo/toolbelt/quick slots.
            gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
            gdm = self._mem.read_ptr(gdm_ptr_addr)
            game_data = self._mem.read_ptr(gdm + 0x10) if gdm else 0

            st.equipment |= {
                "primary_left_wep": self._mem.read_i32(base_addr + 0x32C),
                "primary_right_wep": self._mem.read_i32(base_addr + 0x330),
                "secondary_left_wep": self._mem.read_i32(base_addr + 0x334),
                "secondary_right_wep": self._mem.read_i32(base_addr + 0x338),
                "tertiary_left_wep": self._mem.read_i32(base_addr + 0x33C),
                "tertiary_right_wep": self._mem.read_i32(base_addr + 0x340),
                "helmet": self._mem.read_i32(base_addr + 0x35C),
                "armor": self._mem.read_i32(base_addr + 0x360),
                "gauntlet": self._mem.read_i32(base_addr + 0x364),
                "leggings": self._mem.read_i32(base_addr + 0x368),
                "ring_1": self._mem.read_i32(base_addr + 0x370),
                "ring_2": self._mem.read_i32(base_addr + 0x374),
                "ring_3": self._mem.read_i32(base_addr + 0x378),
                "ring_4": self._mem.read_i32(base_addr + 0x37C),
                "covenant": self._mem.read_i32(base_addr + 0x380),
            }

            if game_data:
                st.equipment |= {
                    "primary_arrow": self._mem.read_i32(game_data + 0x344),
                    "primary_bolt": self._mem.read_i32(game_data + 0x348),
                    "secondary_arrow": self._mem.read_i32(game_data + 0x34C),
                    "secondary_bolt": self._mem.read_i32(game_data + 0x350),
                }

                # Quick items and toolbelt offsets come from DS3 manager's utility/players.py Offsets class.
                quick_item_offsets = {
                    1: 0x5AC,
                    2: 0x5B0,
                    3: 0x5B4,
                    4: 0x5B8,
                    5: 0x5BC,
                    6: 0x5C0,
                    7: 0x5C4,
                    8: 0x5C8,
                    9: 0x5CC,
                    10: 0x5D0,
                }
                toolbelt_offsets = {1: 0x5D4, 2: 0x5D8, 3: 0x5DC, 4: 0x5E0, 5: 0x5E4}
                for slot, off in quick_item_offsets.items():
                    qid = self._mem.read_u32(game_data + off) & 0x0FFFFFFF
                    st.equipment[f"quick_item_{slot}"] = int(qid)
                for slot, off in toolbelt_offsets.items():
                    tid = self._mem.read_u32(game_data + off) & 0x0FFFFFFF
                    st.equipment[f"toolbelt_{slot}"] = int(tid)

                # Spell slots: spell_base = *( *(GameDataMan+0x10) + 0x470 )
                try:
                    spell_base = self._mem.read_ptr(game_data + 0x470)
                    spell_offsets = [
                        0x18,
                        0x20,
                        0x28,
                        0x30,
                        0x38,
                        0x40,
                        0x48,
                        0x50,
                        0x58,
                        0x60,
                        0x68,
                        0x70,
                        0x78,
                        0x80,
                    ]
                    for i, off in enumerate(spell_offsets):
                        sid = self._mem.read_u32(spell_base + off) & 0x0FFFFFFF
                        st.equipment[f"magic_slot_{i}"] = (
                            -1 if sid in (0x0FFFFFFF, 0xFFFFFFFF) else int(sid)
                        )
                except Exception:
                    pass

            return st
        except Exception:
            return st
