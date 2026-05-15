import contextlib
from dataclasses import dataclass
from typing import Any

from phantom_backend.core.errors import PhantomError
from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets
from phantom_backend.services.pot_groups import get_flask_groups, get_pot_groups


@dataclass(frozen=True)
class _ERLayout:
    equip_game_data_off: int = 0x2B0
    inventory_list_off: int = 0x10
    inv_entry_size: int = 0x18
    inv_id_off: int = 0x04
    tail_data_idx_off: int = 0x1C


class EquipApplyService:
    """Apply equipment by calling the game's equip/give functions.

    Uses AOB-resolved function addresses (no static offsets in code).
    """

    def __init__(self, *, mem: MemoryClient, resolver: SymbolResolver, game_key: str):
        self._mem = mem
        self._resolver = resolver
        self._game = game_key

    def apply_build(self, *, player_num: int, equipment: dict[str, Any]) -> None:
        if player_num != 0:
            raise PhantomError("Equipping is only supported for local player_num=0")
        if self._game == "eldenring":
            self._apply_eldenring(equipment)
            return
        if self._game == "ds3":
            self._apply_ds3(equipment)
            return
        raise PhantomError(f"EquipApplyService not implemented for game: {self._game}")

    # -----------------
    # Elden Ring
    # -----------------
    def _apply_eldenring(self, equipment: dict[str, Any]) -> None:
        cfg = load_manager_offsets("eldenring")
        item_types = cfg.get("item_types", {})
        WEAPON = get_hex_int(item_types, "WEAPON")
        ARMOR = get_hex_int(item_types, "ARMOR")
        ACCESSORY = get_hex_int(item_types, "ACCESSORY")
        GOODS = get_hex_int(item_types, "GOODS")
        OTHER = get_hex_int(item_types, "OTHER")

        # Required symbols (AOB-only)
        equip_gear = self._resolver.resolve("EquipGearFunc").address
        equip_goods = self._resolver.resolve("EquipGoodsFunc").address
        item_give = self._resolver.resolve("ItemGiveFunc").address
        remove_item_func = None
        try:
            remove_item_func = self._resolver.resolve("RemoveItemFunc").address
        except Exception:
            remove_item_func = None

        gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
        gdm = self._mem.read_ptr(gdm_ptr_addr)
        if not gdm:
            raise PhantomError("GameDataMan pointer is null")

        player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")
        equip_inv_off = get_hex_int(cfg, "equipment", "equip_inventory_data")
        player_game_data = self._mem.read_ptr(gdm + player_game_data_off)
        if not player_game_data:
            raise PhantomError("PlayerGameData pointer is null")

        lay = _ERLayout()
        equip_game_data = player_game_data + lay.equip_game_data_off

        equip_inventory_data = self._mem.read_ptr(player_game_data + equip_inv_off)
        if not equip_inventory_data:
            raise PhantomError("EquipInventoryData pointer is null")

        # Allocate shared scratch regions in the remote process
        equip_data = self._mem.allocate(0x40)
        item_give_data = self._mem.allocate(0x200)
        try:
            errors: dict[str, str] = {}
            warnings: dict[str, str] = {}
            PotGroups = get_pot_groups()

            def norm(v: Any) -> int:
                if v is None:
                    return 0
                if isinstance(v, dict) and "id" in v:
                    return int(v["id"])
                return int(v)

            slot_map = {
                "primary_left_wep": 0,
                "primary_right_wep": 1,
                "secondary_left_wep": 2,
                "secondary_right_wep": 3,
                "tertiary_left_wep": 4,
                "tertiary_right_wep": 5,
                "primary_arrow": 6,
                "primary_bolt": 7,
                "secondary_arrow": 8,
                "secondary_bolt": 9,
                "tertiary_arrow": 10,
                "tertiary_bolt": 11,
                "helmet": 12,
                "armor": 13,
                "gauntlet": 14,
                "leggings": 15,
                "hair": 16,
                "accessory_1": 17,
                "accessory_2": 18,
                "accessory_3": 19,
                "accessory_4": 20,
                "accessory_5": 21,
                # Quick items 22..31 are supported if provided as quick_item_1..quick_item_10
                "quick_item_1": 22,
                "quick_item_2": 23,
                "quick_item_3": 24,
                "quick_item_4": 25,
                "quick_item_5": 26,
                "quick_item_6": 27,
                "quick_item_7": 28,
                "quick_item_8": 29,
                "quick_item_9": 30,
                "quick_item_10": 31,
                "physick_tear_1": 32,
                "physick_tear_2": 33,
            }

            def _inventory_list() -> int:
                return self._mem.read_ptr(equip_inventory_data + lay.inventory_list_off)

            def _tail_data_idx() -> int:
                try:
                    return self._mem.read_i32(
                        equip_inventory_data + lay.tail_data_idx_off
                    )
                except Exception:
                    return 0

            def _get_item_idx(item_id: int) -> int | None:
                # Inventory lists to scan: Main (0x10) and Key Items (0x20)
                inv_lists = []

                main_inv = _inventory_list()
                if main_inv:
                    inv_lists.append(main_inv)
                # Scan Main (0x10) and Key Items (0x20)
                # Note: The returned index is ambiguous if we don't know which list it came from.
                # However, for simple "Check Existence" checks, this is sufficient.
                # _equip_slot IS NOT SAFE to use with indices from the secondary list!

                offsets = [
                    lay.inventory_list_off,
                    lay.inventory_list_off + 0x10,
                ]  # 0x10, 0x20

                inv_entry_size = lay.inv_entry_size
                inv_id_off = lay.inv_id_off

                want = item_id & 0xFFFFFFFF
                want_base = want & 0x0FFFFFFF
                is_goods = (want & 0xF0000000) == 0x40000000

                for off in offsets:
                    try:
                        inv = self._mem.read_ptr(equip_inventory_data + off)
                    except Exception:
                        continue

                    if not inv:
                        continue

                    for i in range(2688):
                        cur_raw = self._mem.read_i32(
                            inv + i * inv_entry_size + inv_id_off
                        )
                        if cur_raw == -1:
                            continue

                        cur = cur_raw & 0xFFFFFFFF
                        if cur == want:
                            return i

                        # Fuzzy match for GOODS
                        if is_goods and (cur & 0x0FFFFFFF) == want_base:
                            return i

                return None

            def _get_item_indices(item_id: int) -> list[int]:
                inv = _inventory_list()
                if not inv:
                    return []
                want = item_id & 0xFFFFFFFF
                out: list[int] = []
                for i in range(2688):
                    cur = self._mem.read_i32(
                        inv + i * lay.inv_entry_size + lay.inv_id_off
                    )
                    if cur != -1:
                        cur &= 0xFFFFFFFF
                    if (cur & 0xFFFFFFFF) == want:
                        out.append(i)
                return out

            def _overwrite_inventory_entry_id(idx: int, full_item_id: int) -> None:
                inv = _inventory_list()
                if not inv:
                    return
                base = inv + idx * lay.inv_entry_size
                # Keep both item ID fields in sync.
                self._mem.write_u32(base + 0x0, int(full_item_id) & 0xFFFFFFFF)
                self._mem.write_u32(
                    base + lay.inv_id_off, int(full_item_id) & 0xFFFFFFFF
                )

            def _delete_item_at_idx(idx: int) -> None:
                inv = _inventory_list()
                if not inv:
                    return
                base = inv + idx * lay.inv_entry_size
                self._mem.write_u32(base + 0x0, 0xFFFFFFFF)
                self._mem.write_u32(base + lay.inv_id_off, 0xFFFFFFFF)

            def _remove_item_by_id(full_item_id: int) -> bool:
                idx = _get_item_idx(full_item_id)
                if idx is None:
                    return False
                if remove_item_func is None:
                    _delete_item_at_idx(idx)
                    return True
                final_idx = int(idx + _tail_data_idx())
                sc = bytes(
                    [
                        0x48,
                        0x83,
                        0xEC,
                        0x28,  # sub rsp, 28h
                        0x48,
                        0xB9,  # mov rcx, equip_inventory_data
                        *int(equip_inventory_data).to_bytes(8, "little"),
                        0x48,
                        0xBA,  # mov rdx, final_idx
                        *int(final_idx).to_bytes(8, "little"),
                        0x41,
                        0xB8,
                        0x01,
                        0x00,
                        0x00,
                        0x00,  # mov r8d, 1
                        0xFF,
                        0x15,
                        0x02,
                        0x00,
                        0x00,
                        0x00,  # call [rip+2]
                        0xEB,
                        0x08,  # jmp over addr
                        *int(remove_item_func).to_bytes(8, "little"),
                        0x48,
                        0x83,
                        0xC4,
                        0x28,  # add rsp, 28h
                        0xC3,  # ret
                    ]
                )
                _run_shellcode(sc, timeout_ms=200)
                return _get_item_idx(full_item_id) is None

            def _get_item_by_idx(idx: int) -> int:
                inv = _inventory_list()
                return self._mem.read_i32(inv + idx * lay.inv_entry_size)

            def _update_quantity(idx: int, quantity: int) -> None:
                inv = _inventory_list()
                if not inv:
                    return
                base = inv + idx * lay.inv_entry_size
                # Quantity is at +0x08
                self._mem.write_u32(base + 0x08, int(quantity) & 0xFFFFFFFF)

            def _run_shellcode(code: bytes, timeout_ms: int = 250) -> None:
                buf = self._mem.allocate(len(code))
                try:
                    self._mem.write_bytes(buf, code)
                    self._mem.start_thread(buf)
                finally:
                    self._mem.free(buf)

            def _give_item(
                full_item_id: int,
                *,
                quantity: int = 1,
                reinforce_level: int = -1,
                gem: int = -1,
            ) -> int | None:
                item_table_mem = item_give_data + 32
                self._mem.write_u32(item_table_mem, 1)
                self._mem.write_u32(item_table_mem + 4, full_item_id & 0xFFFFFFFF)
                self._mem.write_u32(item_table_mem + 8, int(quantity) & 0xFFFFFFFF)
                self._mem.write_u32(
                    item_table_mem + 12, int(reinforce_level) & 0xFFFFFFFF
                )
                self._mem.write_u32(item_table_mem + 16, int(gem) & 0xFFFFFFFF)

                # sub rsp, 28h
                # mov rcx, gdm
                # mov rdx, item_table_mem
                # mov r8, item_give_data
                # mov r9d, 0
                # call item_give
                # add rsp, 28h; ret
                sc = bytes(
                    [
                        0x48,
                        0x83,
                        0xEC,
                        0x28,
                        0x48,
                        0xB9,
                        *int(gdm).to_bytes(8, "little"),
                        0x48,
                        0xBA,
                        *int(item_table_mem).to_bytes(8, "little"),
                        0x49,
                        0xB8,
                        *int(item_give_data).to_bytes(8, "little"),
                        0x41,
                        0xB9,
                        0x00,
                        0x00,
                        0x00,
                        0x00,
                        0xFF,
                        0x15,
                        0x02,
                        0x00,
                        0x00,
                        0x00,
                        0xEB,
                        0x08,
                        *int(item_give).to_bytes(8, "little"),
                        0x48,
                        0x83,
                        0xC4,
                        0x28,
                        0xC3,
                    ]
                )
                _run_shellcode(sc, timeout_ms=200)
                return _get_item_idx(full_item_id)

            def _give_item_new_idx(
                full_item_id: int,
                *,
                quantity: int = 1,
                reinforce_level: int = -1,
                gem: int = -1,
            ) -> int | None:
                """Give an item and return the *newly-created* inventory index if possible.

                This is required when the same weapon needs to be equipped into multiple slots.
                """
                before = set(_get_item_indices(full_item_id))
                _ = _give_item(
                    full_item_id,
                    quantity=quantity,
                    reinforce_level=reinforce_level,
                    gem=gem,
                )
                after = _get_item_indices(full_item_id)
                for idx in after:
                    if idx not in before:
                        return idx
                return after[0] if after else None

            def _ensure_item_exists(
                full_item_id: int, *, quantity: int = 1
            ) -> int | None:
                idx = _get_item_idx(full_item_id)
                if idx is not None:
                    return idx
                return _give_item(full_item_id, quantity=quantity)

            def _equip_slot(slot: int, idx: int) -> None:
                tail = _tail_data_idx()
                if idx != -1:
                    item_id0 = _get_item_by_idx(idx)
                    self._mem.write_u32(equip_data + 0x10, item_id0 & 0xFFFFFFFF)
                else:
                    self._mem.write_u32(equip_data + 0x10, 0xFFFFFFFF)
                    tail = 0

                if slot == 32:
                    val = 0xFFFFFFFF
                    if idx != -1:
                        inv = _inventory_list()
                        val = self._mem.read_u32(
                            inv + idx * lay.inv_entry_size + lay.inv_id_off
                        )

                    self._mem.write_u32(equip_game_data + 0x3E4, val)
                    return
                elif slot == 33:
                    val = 0xFFFFFFFF
                    if idx != -1:
                        inv = _inventory_list()
                        val = self._mem.read_u32(
                            inv + idx * lay.inv_entry_size + lay.inv_id_off
                        )

                    self._mem.write_u32(equip_game_data + 0x3E8, val)
                    return

                final_idx = (idx + tail) if idx != -1 else -1

                if slot <= 21:
                    equip_func = equip_gear
                    extra_args = [1, 1, 0]
                else:
                    equip_func = equip_goods
                    slot = slot - 22
                    extra_args = []

                sc = bytearray(
                    [
                        0x48,
                        0x83,
                        0xEC,
                        0x38,
                        0x48,
                        0xB9,
                        *int(equip_game_data).to_bytes(8, "little"),
                        0xBA,
                        *int(slot).to_bytes(4, "little"),
                        0x49,
                        0xB8,
                        *int(equip_data + 0x10).to_bytes(8, "little"),
                        0x41,
                        0xB9,
                        *int(final_idx).to_bytes(4, "little", signed=True),
                    ]
                )

                if extra_args:
                    for i, arg in enumerate(extra_args):
                        sc.extend(
                            [
                                0xC7,
                                0x44,
                                0x24,
                                0x20 + i * 8,
                                *int(arg).to_bytes(4, "little"),
                            ]
                        )

                sc.extend(
                    [
                        0x48,
                        0xB8,
                        *int(equip_func).to_bytes(8, "little"),
                        0xFF,
                        0xD0,
                        0x48,
                        0x83,
                        0xC4,
                        0x38,
                        0xC3,
                    ]
                )
                _run_shellcode(bytes(sc), timeout_ms=200)

            def _check_slot_has_group_pot(slot: int, group_num: int) -> bool:
                if not (22 <= slot <= 31):
                    return False
                try:
                    qi = slot - 22
                    quick_item_offset = 0x1C0 + (qi * 4)
                    cur = self._mem.read_i32(equip_game_data + quick_item_offset)
                    if cur in (-1, 0xFFFFFFFF):
                        return False
                    base_id = cur & 0x0FFFFFFF
                    return base_id in PotGroups.get_group_items(group_num)
                except Exception:
                    return False

            def _equip_pot_quick_item(
                base_id: int, slot: int, quantity: int | None = None
            ) -> bool:
                group_num = PotGroups.get_group_for_item(int(base_id))
                if group_num is None:
                    return False

                # Unequip any already-equipped pot from this group (avoid conflicts/crashes)
                for s in range(22, 32):
                    if _check_slot_has_group_pot(s, group_num):
                        _equip_slot(s, -1)

                want_full = GOODS | (int(base_id) & 0x0FFFFFFF)

                # If desired pot exists, equip it.
                idx = _get_item_idx(want_full)
                if idx is not None:
                    if quantity is not None:
                        _update_quantity(idx, quantity)
                    _equip_slot(slot, idx)
                    return True

                # Otherwise: if any pot from this group exists in inventory, reuse it by rewriting the ID.
                for other_base in PotGroups.get_group_items(group_num):
                    other_full = GOODS | (int(other_base) & 0x0FFFFFFF)
                    other_idx = _get_item_idx(other_full)
                    if other_idx is None:
                        continue
                    _overwrite_inventory_entry_id(other_idx, want_full)
                    if quantity is not None:
                        _update_quantity(other_idx, quantity)
                    _equip_slot(slot, other_idx)
                    return True

                # As a last resort, try to give the pot.
                idx = _give_item(
                    want_full, quantity=quantity if quantity is not None else 99
                )
                if idx is None:
                    return False
                _equip_slot(slot, idx)
                return True

            used_weapon_idxs: set[int] = set()

            def _equip_weapon_with_aow(
                weapon_id: int, ash_of_war_id: int, slot: int
            ) -> None:
                weapon_full = WEAPON | (weapon_id & 0x0FFFFFFF)
                ash_base = ash_of_war_id & 0x0FFFFFFF

                # Try OTHER first, then GOODS.
                ash_added = False
                ash_full: int | None = None
                for t in (OTHER, GOODS):
                    candidate = t | ash_base
                    if _ensure_item_exists(candidate, quantity=1) is not None:
                        ash_added = True
                        ash_full = candidate
                        break

                # Remove existing base copy, then create and equip a fresh AoW variant.
                _remove_item_by_id(weapon_full)

                idx = _give_item(weapon_full, quantity=1, gem=int(ash_base))
                if idx is None:
                    raise PhantomError("Failed to get/add weapon with Ash of War")

                # Add the ash back if we successfully ensured it earlier.
                if ash_added and ash_full is not None:
                    with contextlib.suppress(Exception):
                        _ensure_item_exists(ash_full, quantity=1)

                _equip_slot(slot, idx)
                used_weapon_idxs.add(idx)

            def _equip_any_item(
                item_id: int, slot: int, quantity: int | None = None
            ) -> bool:
                # Unequip / empty
                if item_id in (-1, 0x0FFFFFFF, 0xFFFFFFFF):
                    if 32 <= slot <= 33:
                        # Direct write unequip for Physick
                        offset = 0x3E4 + (slot - 32) * 4
                        self._mem.write_u32(equip_game_data + offset, 0xFFFFFFFF)
                        return True

                    if 0 <= slot <= 5:
                        item_id = 110000
                    elif slot == 12:
                        item_id = 10000
                    elif slot == 13:
                        item_id = 10100
                    elif slot == 14:
                        item_id = 10200
                    elif slot == 15:
                        item_id = 10300
                    else:
                        _equip_slot(slot, -1)
                        return True

                # Ash of War handling: weapon entries may be dicts: {"id": X, "ash_of_war": Y}
                # Only apply on weapon slots (0-5). Other weapon slots (6-11) are arrows/bolts.
                raw = equipment.get(
                    next((k for k, v in slot_map.items() if v == slot), "")
                )
                if (
                    0 <= slot <= 5
                    and isinstance(raw, dict)
                    and "id" in raw
                    and "ash_of_war" in raw
                    and raw.get("ash_of_war") not in (None, -1, 0xFFFFFFFF, 0x0FFFFFFF)
                ):
                    _equip_weapon_with_aow(int(raw["id"]), int(raw["ash_of_war"]), slot)
                    return True

                # Determine type bits based on slot category.
                if 0 <= slot <= 11:
                    full = WEAPON | (item_id & 0x0FFFFFFF)
                elif 12 <= slot <= 15:
                    full = ARMOR | (item_id & 0x0FFFFFFF)
                elif 17 <= slot <= 21:
                    full = ACCESSORY | (item_id & 0x0FFFFFFF)
                elif 22 <= slot <= 31:
                    base_id = item_id & 0x0FFFFFFF
                    # Try direct goods equip first, then fallback to group handling.
                    full = GOODS | base_id
                elif 32 <= slot <= 33:
                    full = GOODS | (item_id & 0x0FFFFFFF)
                else:
                    full = item_id & 0xFFFFFFFF

                # Physick Slot Special Handling (32, 33)
                if 32 <= slot <= 33:
                    # 0. Ensure user has the Flask of Wondrous Physick (ID 250, Category GOODS)
                    # ID 250 | GOODS = 0x400000FA
                    flask_id = 0x400000FA
                    if _get_item_idx(flask_id) is None:
                        _give_item(flask_id, quantity=1)

                    # 1. Ensure we have the Tear (scanning all lists)
                    idx = _get_item_idx(full)
                    if idx is None:
                        # Give strict quantity=1
                        idx = _give_item(full, quantity=1)

                    # 2. Direct Write ID (Bypassing _equip_slot to avoid List Pointer issues)
                    # Use 'full' which has the correct ID + GOODS flag.
                    offset = 0x3E4 + (slot - 32) * 4
                    self._mem.write_u32(equip_game_data + offset, full & 0xFFFFFFFF)
                    return True

                # For weapon-like slots, we must ensure a distinct inventory entry per slot when duplicates exist.
                if 0 <= slot <= 11:
                    candidates = [
                        i for i in _get_item_indices(full) if i not in used_weapon_idxs
                    ]
                    idx = candidates[0] if candidates else None
                    if idx is None:
                        safe_qty = quantity if quantity is not None else 99
                        qt = 1 if slot <= 5 else safe_qty
                        idx = _give_item_new_idx(full, quantity=qt)
                    if idx is not None:
                        if 6 <= slot <= 11 and quantity is not None:
                            _update_quantity(idx, quantity)
                        used_weapon_idxs.add(idx)
                else:
                    idx = _get_item_idx(full)
                    if idx is None:
                        idx = _give_item(
                            full, quantity=quantity if quantity is not None else 99
                        )
                    elif 22 <= slot <= 31 and quantity is not None:
                        _update_quantity(idx, quantity)
                if idx is None:
                    # Non-quick slots are treated as hard failures.
                    if 22 <= slot <= 31:
                        if (
                            PotGroups.get_group_for_item(int(item_id & 0x0FFFFFFF))
                            is not None
                        ):
                            return _equip_pot_quick_item(
                                int(item_id & 0x0FFFFFFF), slot, quantity=quantity
                            )
                        return False
                    raise PhantomError(f"Failed to get/add item {full:08X}")
                _equip_slot(slot, idx)
                return True

            # Clear quick slots first, then run normal equip pass.
            for key, slot in slot_map.items():
                if not key.startswith("quick_item_") or key not in equipment:
                    continue
                try:
                    val = equipment[key]
                    item_id = norm(val)
                    if item_id in (-1, 0x0FFFFFFF, 0xFFFFFFFF):
                        _equip_slot(slot, -1)
                except Exception as e:
                    errors[key] = str(e)

            for key, slot in slot_map.items():
                if key not in equipment:
                    continue
                try:
                    val = equipment[key]
                    item_id = norm(val)
                    if key.startswith("quick_item_") and item_id in (
                        -1,
                        0x0FFFFFFF,
                        0xFFFFFFFF,
                    ):
                        continue
                    qty = None
                    if isinstance(val, dict) and "count" in val:
                        qty = int(val["count"])

                    ok = _equip_any_item(item_id, slot, quantity=qty)
                    if not ok and key.startswith("quick_item_"):
                        want = item_id & 0x0FFFFFFF
                        warnings[key] = (
                            f"Quick item {want} not found in inventory and could not be given. "
                            f"Fix: obtain it in-game (or remove it from the build) then re-apply."
                        )
                        # If we can't equip the desired quick item, clear the slot to avoid
                        # leaving a broken/invalid quick item equipped.
                        with contextlib.suppress(Exception):
                            _equip_slot(slot, -1)
                except Exception as e:
                    errors[key] = str(e)

            # Magic slots: manually ensure inventory + write memory (since no equip func)
            magic_base_off = get_hex_int(cfg, "equipment", "magic_slots_base")
            spell_base = self._mem.read_ptr(player_game_data + magic_base_off)
            magic_slot_offsets = cfg.get("equipment", {}).get("magic_slot_offsets", {})

            # Clear explicitly empty magic slots before writing populated ones.
            for i in range(14):
                key = f"magic_slot_{i}"
                if key not in equipment:
                    continue
                try:
                    want = norm(equipment[key])
                    if want not in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
                        continue
                    off_val = magic_slot_offsets.get(f"slot_{i}")
                    if off_val:
                        off = int(str(off_val), 16)
                        self._mem.write_u32(spell_base + off, 0xFFFFFFFF)
                except Exception as e:
                    errors[key] = str(e)

            for i in range(14):
                key = f"magic_slot_{i}"
                if key not in equipment:
                    continue
                try:
                    want = norm(equipment[key])
                    # If empty slot
                    if want in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
                        continue

                    # If valid spell, ensure in inventory (GOODS)
                    full = GOODS | (want & 0x0FFFFFFF)
                    idx = _get_item_idx(full)
                    if idx is None:
                        idx = _give_item(full, quantity=1)

                    # Write to memory (the essential part for magic to work)
                    off_val = magic_slot_offsets.get(f"slot_{i}")
                    if off_val:
                        off = int(str(off_val), 16)
                        write_addr = spell_base + off
                        write_val = want & 0xFFFFFFFF
                        self._mem.write_u32(write_addr, write_val)

                except Exception as e:
                    errors[key] = str(e)

            if errors:
                # Prefer a single actionable message: errors are fatal; warnings are informational.
                msg = {"errors": errors}
                if warnings:
                    msg["warnings"] = warnings
                raise PhantomError(f"Build apply failed: {msg}")
        finally:
            self._mem.free(equip_data)
            self._mem.free(item_give_data)

    # -----------------
    # Dark Souls 3
    # -----------------
    def _apply_ds3(self, equipment: dict[str, Any]) -> None:
        cfg = load_manager_offsets("ds3")
        item_types = cfg.get("item_types", {})
        WEAPON = get_hex_int(item_types, "WEAPON")
        ARMOR = get_hex_int(item_types, "ARMOR")
        ACCESSORY = get_hex_int(item_types, "ACCESSORY")
        GOODS = get_hex_int(item_types, "GOODS")

        equip_gear = self._resolver.resolve("EquipGearFunc").address
        equip_goods = self._resolver.resolve("EquipGoodsFunc").address
        item_give = self._resolver.resolve("ItemGiveFunc").address

        gdm_ptr_addr = self._resolver.resolve("GameDataManPtrAddr").address
        gdm = self._mem.read_ptr(gdm_ptr_addr)
        if not gdm:
            raise PhantomError("GameDataMan pointer is null")

        player_game_data_off = get_hex_int(cfg, "equipment", "player_game_data")
        player_game_data = self._mem.read_ptr(gdm + player_game_data_off)
        if not player_game_data:
            raise PhantomError("PlayerGameData pointer is null")

        equip_game_data = player_game_data + 0x228
        equip_inventory_data = player_game_data + 0x3D0  # inline struct, not a pointer
        inv_list_off = 0x18
        inv_entry_size = 0x10
        inv_id_off = 0x04
        tail_data_idx_off = 0x24

        equip_data = self._mem.allocate(0x40)
        item_give_data = self._mem.allocate(0x200)
        try:
            errors: dict[str, str] = {}
            warnings: dict[str, str] = {}
            FlaskGroups = get_flask_groups()

            def norm(v: Any) -> int:
                if v is None:
                    return 0
                if isinstance(v, dict) and "id" in v:
                    return int(v["id"])
                return int(v)

            slot_map = {
                "primary_left_wep": 0,
                "primary_right_wep": 1,
                "secondary_left_wep": 2,
                "secondary_right_wep": 3,
                "tertiary_left_wep": 4,
                "tertiary_right_wep": 5,
                "primary_arrow": 6,
                "primary_bolt": 7,
                "secondary_arrow": 8,
                "secondary_bolt": 9,
                "tertiary_arrow": 10,
                "tertiary_bolt": 11,
                "helmet": 12,
                "armor": 13,
                "gauntlet": 14,
                "leggings": 15,
                "ring_1": 17,
                "ring_2": 18,
                "ring_3": 19,
                "ring_4": 20,
                "accessory_1": 17,
                "accessory_2": 18,
                "accessory_3": 19,
                "accessory_4": 20,
                # Quick items + toolbelt (goods)
                "quick_item_1": 22,
                "quick_item_2": 23,
                "quick_item_3": 24,
                "quick_item_4": 25,
                "quick_item_5": 26,
                "quick_item_6": 27,
                "quick_item_7": 28,
                "quick_item_8": 29,
                "quick_item_9": 30,
                "quick_item_10": 31,
                "toolbelt_1": 32,
                "toolbelt_2": 33,
                "toolbelt_3": 34,
                "toolbelt_4": 35,
                "toolbelt_5": 36,
                "covenant": 21,
            }

            def _inventory_list() -> int:
                return self._mem.read_ptr(equip_inventory_data + inv_list_off)

            def _tail_data_idx() -> int:
                try:
                    return self._mem.read_i32(equip_inventory_data + tail_data_idx_off)
                except Exception:
                    return 0

            def _get_item_idx(item_id: int) -> int | None:
                inv = _inventory_list()
                if not inv:
                    return None
                want = item_id & 0xFFFFFFFF
                # Keep a bounded scan to avoid long reads.
                for i in range(5000):
                    cur = self._mem.read_i32(inv + i * inv_entry_size + inv_id_off)
                    if cur != -1:
                        cur &= 0xFFFFFFFF
                    if (cur & 0xFFFFFFFF) == want:
                        return i
                return None

            def _get_item_by_idx(idx: int) -> int:
                inv = _inventory_list()
                return self._mem.read_i32(inv + idx * inv_entry_size)

            def _run_shellcode(code: bytes, timeout_ms: int = 300) -> None:
                buf = self._mem.allocate(len(code))
                try:
                    self._mem.write_bytes(buf, code)
                    self._mem.start_thread(buf)
                finally:
                    self._mem.free(buf)

            def _give_item(
                full_item_id: int, quantity: int = 1, upgrade_level: int = 0
            ) -> int | None:
                # Populate both item table buffers used by the give-item call.

                # RDX: ItemToSpawn
                item_table_mem = item_give_data + 32
                self._mem.write_u32(item_table_mem, 1)  # Counter
                self._mem.write_u32(item_table_mem + 4, full_item_id & 0xFFFFFFFF)
                self._mem.write_u32(item_table_mem + 8, int(quantity) & 0xFFFFFFFF)
                self._mem.write_u32(item_table_mem + 12, 0xFFFFFFFF)  # Durability
                self._mem.write_u32(item_table_mem + 16, 0xFFFFFFFF)  # Padding?

                # R8: ItemGibData (at +0)
                # Layout: Qty, ID, Durability, Infusion, UpgradeLevel
                self._mem.write_u32(item_give_data, int(quantity) & 0xFFFFFFFF)
                self._mem.write_u32(item_give_data + 4, full_item_id & 0xFFFFFFFF)
                self._mem.write_u32(item_give_data + 8, 0xFFFFFFFF)  # Durability
                self._mem.write_u32(
                    item_give_data + 12, 0
                )  # Infusion (Gems not supported yet)
                self._mem.write_u32(
                    item_give_data + 16, int(upgrade_level) & 0xFFFFFFFF
                )

                sc = bytes(
                    [
                        0x48,
                        0x83,
                        0xEC,
                        0x28,
                        0x48,
                        0xB9,
                        *int(gdm).to_bytes(8, "little"),
                        0x48,
                        0xBA,
                        *int(item_table_mem).to_bytes(8, "little"),
                        0x49,
                        0xB8,
                        *int(item_give_data).to_bytes(8, "little"),
                        0x41,
                        0xB9,
                        0x00,
                        0x00,
                        0x00,
                        0x00,
                        0xFF,
                        0x15,
                        0x02,
                        0x00,
                        0x00,
                        0x00,
                        0xEB,
                        0x08,
                        *int(item_give).to_bytes(8, "little"),
                        0x48,
                        0x83,
                        0xC4,
                        0x28,
                        0xC3,
                    ]
                )
                _run_shellcode(sc, timeout_ms=250)
                return _get_item_idx(full_item_id)

            def _equip_slot(slot: int, idx: int) -> None:
                tail = _tail_data_idx()
                if idx != -1:
                    item_id0 = _get_item_by_idx(idx)
                    self._mem.write_u32(equip_data + 0x10, item_id0 & 0xFFFFFFFF)
                else:
                    self._mem.write_u32(equip_data + 0x10, 0xFFFFFFFF)
                    tail = 0

                final_idx = (idx + tail) if idx != -1 else -1

                if slot <= 21:
                    equip_func = equip_gear
                    extra_args = [1, 1, 0]
                elif slot <= 38:
                    equip_func = equip_goods
                    slot = slot - 22
                    extra_args = []
                else:
                    raise PhantomError(f"Unsupported DS3 equip slot: {slot}")

                sc = bytearray(
                    [
                        0x48,
                        0x83,
                        0xEC,
                        0x38,
                        0x48,
                        0xB9,
                        *int(equip_game_data).to_bytes(8, "little"),
                        0xBA,
                        *int(slot).to_bytes(4, "little"),
                        0x49,
                        0xB8,
                        *int(equip_data + 0x10).to_bytes(8, "little"),
                        0x41,
                        0xB9,
                        *int(final_idx).to_bytes(4, "little", signed=True),
                    ]
                )
                if extra_args:
                    for i, arg in enumerate(extra_args):
                        sc.extend(
                            [
                                0xC7,
                                0x44,
                                0x24,
                                0x20 + i * 4,
                                *int(arg).to_bytes(4, "little"),
                            ]
                        )

                sc.extend(
                    [
                        0x48,
                        0xB8,
                        *int(equip_func).to_bytes(8, "little"),
                        0xFF,
                        0xD0,
                        0x48,
                        0x83,
                        0xC4,
                        0x38,
                        0xC3,
                    ]
                )
                _run_shellcode(bytes(sc), timeout_ms=250)

            def _check_slot_has_flask(slot: int, group_num: int) -> bool:
                if not (22 <= slot <= 31):
                    return False
                try:
                    qi = slot - 22
                    quick_item_offset = 0x1C0 + (qi * 4)
                    cur = self._mem.read_i32(equip_game_data + quick_item_offset)
                    if cur in (-1, 0xFFFFFFFF):
                        return False
                    base_id = cur & 0x0FFFFFFF
                    return base_id in FlaskGroups.get_group_items(group_num)
                except Exception:
                    return False

            def _delete_ds3_item(idx: int) -> None:
                inv = _inventory_list()
                if not inv:
                    return
                # Write -1 to ID at +4 to mark as deleted/empty
                self._mem.write_u32(inv + idx * inv_entry_size + 4, 0xFFFFFFFF)

            def _scan_inventory_for_group(group_num: int) -> int | None:
                inv = _inventory_list()
                if not inv:
                    return None
                # Scan same range as _get_item_idx (5000)
                group_items = FlaskGroups.get_group_items(group_num)
                for i in range(5000):
                    cur_val = self._mem.read_i32(inv + i * inv_entry_size + inv_id_off)
                    if cur_val == -1:
                        continue
                    cur_val &= 0xFFFFFFFF
                    type_bits = (cur_val >> 28) & 0xF
                    item_base = cur_val & 0x0FFFFFFF
                    if type_bits == 0x4 and item_base in group_items:
                        return i
                return None

            def _equip_ds3_flask(base_id: int, slot: int) -> bool:
                group_num = FlaskGroups.get_group_for_item(int(base_id))
                if group_num is None:
                    return False

                full_id = GOODS | (int(base_id) & 0x0FFFFFFF)

                # 1. Try exact match first
                idx = _get_item_idx(full_id)
                if idx is not None:
                    if 22 <= slot <= 31 and _check_slot_has_flask(slot, group_num):
                        _equip_slot(slot, -1)
                    _equip_slot(slot, idx)
                    return True

                # 2. Try alternative (empty/full)
                is_filled = (base_id % 2) == 1
                if is_filled:
                    empty_base = base_id - 1
                    empty_full = GOODS | (empty_base & 0x0FFFFFFF)
                    alt_idx = _get_item_idx(empty_full)
                else:
                    full_base = base_id + 1
                    full_full = GOODS | (full_base & 0x0FFFFFFF)
                    alt_idx = _get_item_idx(full_full)

                if alt_idx is not None:
                    if 22 <= slot <= 31 and _check_slot_has_flask(slot, group_num):
                        _equip_slot(slot, -1)
                    _equip_slot(slot, alt_idx)
                    return True

                # 3. Search for ANY flask in group -> DELETE it -> GIVE desired one
                candidate_idx = _scan_inventory_for_group(group_num)
                if candidate_idx is not None:
                    # Unequip slots using this group first.
                    for s in range(22, 32):
                        if _check_slot_has_flask(s, group_num):
                            _equip_slot(s, -1)

                    _delete_ds3_item(candidate_idx)
                    # Give the new item
                    new_idx = _give_item(full_id, quantity=1)
                    if new_idx is not None:
                        _equip_slot(slot, new_idx)
                        return True

                # 4. Fallback: Try giving anyway (maybe we have none)
                new_idx = _give_item(full_id, quantity=1)
                if new_idx is not None:
                    _equip_slot(slot, new_idx)
                    return True

                return False

            def _equip_any_item(item_id: int, slot: int, quantity: int = 99) -> bool:
                if item_id in (-1, 0x0FFFFFFF, 0xFFFFFFFF, 268435455):
                    _equip_slot(slot, -1)
                    return True

                if 0 <= slot <= 11:
                    full = WEAPON | (item_id & 0x0FFFFFFF)
                elif 12 <= slot <= 15:
                    full = ARMOR | (item_id & 0x0FFFFFFF)
                elif 17 <= slot <= 21:
                    full = ACCESSORY | (item_id & 0x0FFFFFFF)
                elif 22 <= slot <= 38:
                    base_id = item_id & 0x0FFFFFFF
                    # Try direct goods equip first, then fallback to flask-group handling.
                    full = GOODS | base_id
                else:
                    full = item_id & 0xFFFFFFFF

                idx = _get_item_idx(full)
                if idx is None:
                    # For weapons, extract upgrade level from ID
                    upgrade_val = 0
                    final_full = full
                    if 0 <= slot <= 11:  # Weapons
                        upgrade_val = full % 10
                        final_full = full - upgrade_val

                    idx = _give_item(
                        final_full,
                        quantity=quantity if (22 <= slot <= 38) else 1,
                        upgrade_level=upgrade_val,
                    )
                if idx is None:
                    # Non-fatal for quick/toolbelt
                    if 22 <= slot <= 38:
                        if (
                            FlaskGroups.get_group_for_item(int(item_id & 0x0FFFFFFF))
                            is not None
                        ):
                            return _equip_ds3_flask(int(item_id & 0x0FFFFFFF), slot)
                        return False
                    raise PhantomError(f"Failed to get/add item {full:08X}")
                _equip_slot(slot, idx)
                return True

            # Clear quick/toolbelt slots first.
            for key, slot in slot_map.items():
                if key not in equipment or not key.startswith(
                    ("quick_item_", "toolbelt_")
                ):
                    continue
                try:
                    cur = norm(equipment[key])
                    if cur in (-1, 0x0FFFFFFF, 0xFFFFFFFF, 268435455):
                        _equip_slot(slot, -1)
                except Exception as e:
                    errors[key] = str(e)

            for key, slot in slot_map.items():
                if key not in equipment:
                    continue
                try:
                    cur = norm(equipment[key])
                    if key.startswith(("quick_item_", "toolbelt_")) and cur in (
                        -1,
                        0x0FFFFFFF,
                        0xFFFFFFFF,
                        268435455,
                    ):
                        continue
                    ok = _equip_any_item(cur, slot)
                    if not ok and (key.startswith(("quick_item_", "toolbelt_"))):
                        want = cur & 0x0FFFFFFF
                        warnings[key] = (
                            f"Item {want} not found in inventory and could not be given."
                        )
                        with contextlib.suppress(Exception):
                            _equip_slot(slot, -1)
                except Exception as e:
                    errors[key] = str(e)

            # Magic slots: manually ensure inventory + write memory (since no equip func)
            magic_base_off = get_hex_int(cfg, "equipment", "magic_slots_base")
            spell_base = self._mem.read_ptr(player_game_data + magic_base_off)
            magic_slot_offsets = cfg.get("equipment", {}).get("magic_slot_offsets", {})

            # Clear explicitly empty magic slots before writing populated ones.
            for i in range(14):
                key = f"magic_slot_{i}"
                if key not in equipment:
                    continue
                try:
                    want = norm(equipment[key])
                    if want not in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
                        continue
                    off_val = magic_slot_offsets.get(f"slot_{i}")
                    if off_val:
                        off = int(str(off_val), 16)
                        self._mem.write_u32(spell_base + off, 0xFFFFFFFF)
                except Exception as e:
                    errors[key] = str(e)

            for i in range(14):
                key = f"magic_slot_{i}"
                if key not in equipment:
                    continue
                try:
                    want = norm(equipment[key])
                    # If empty slot
                    if want in (-1, 0xFFFFFFFF, 0x0FFFFFFF):
                        continue

                    # If valid spell, ensure in inventory (GOODS)
                    full = GOODS | (want & 0x0FFFFFFF)
                    idx = _get_item_idx(full)
                    if idx is None:
                        idx = _give_item(full, quantity=1)

                    off_val = magic_slot_offsets.get(f"slot_{i}")
                    if off_val:
                        off = int(str(off_val), 16)
                        # Write raw ID.
                        self._mem.write_u32(spell_base + off, want & 0xFFFFFFFF)

                except Exception as e:
                    errors[key] = str(e)

            if errors:
                msg = {"errors": errors}
                if warnings:
                    msg["warnings"] = warnings
                raise PhantomError(f"Build apply failed: {msg}")
        finally:
            self._mem.free(equip_data)
            self._mem.free(item_give_data)
