from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from phantom_backend.core.aob import AOBScanner
from phantom_backend.core.errors import PhantomError
from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets


@dataclass(frozen=True)
class CheatInfo:
    name: str
    description: str


_ER_NOWEIGHT_ORIG = {}
_DS3_ARROW_PATCH_ORIG = {}


class CheatsService:
    """Cheat toggles (AOB-only).

    v1 focuses on wiring: API + symbol-driven operations. Actual symbols must be supplied.
    """

    def __init__(self, *, mem: MemoryClient, resolver: SymbolResolver, game_key: str):
        self._mem = mem
        self._resolver = resolver
        self._game = game_key

    def list_cheats(self) -> list[CheatInfo]:
        # Keep stable names (matching your existing CheatManager keys).
        return [
            CheatInfo("NoDead", "Prevents death"),
            CheatInfo("NoDamage", "Prevents taking damage"),
            CheatInfo("NoStaminaConsumption", "Infinite stamina"),
            CheatInfo("NoFPConsumption", "Infinite FP"),
            CheatInfo("NoGoodsConsume", "Consumables not consumed"),
            CheatInfo("NoArrowConsume", "Arrows/bolts not consumed"),
            CheatInfo("NoWeight", "No equipment weight"),
            CheatInfo("NoHit", "No hit / hook-based (game-specific)"),
        ]

    def set_cheat(self, name: str, enable: bool) -> None:
        # Common aliases / typo tolerance
        if name.lower() == "noarrowconume":
            name = "NoArrowConsume"

        # AOB-only: require symbol names per cheat. We keep it simple but structured.
        if name not in {c.name for c in self.list_cheats()}:
            raise PhantomError(f"Unknown cheat: {name}")

        if self._game == "eldenring":
            self._set_er(name, enable)
            return
        if self._game == "ds3":
            self._set_ds3(name, enable)
            return
        raise PhantomError(f"Unsupported game: {self._game}")

    def _set_er(self, name: str, enable: bool) -> None:
        cfg = load_manager_offsets("eldenring")
        bits = cfg.get("cheats", {}).get("bits", {})
        flag_base = get_hex_int(cfg, "cheats", "flag_base")
        no_goods_base = get_hex_int(cfg, "cheats", "no_goods_base")
        no_hit_base = get_hex_int(cfg, "cheats", "no_hit_base")

        # Base chain roots from existing ER cheat logic:
        # - Flag bits (NoDead/NoDamage/NoFP/NoStamina): WorldChrMan > 10EF8 > 0*10 > 190 > 0
        # - NoGoods/NoHit bits: WorldChrMan > 10EF8 > 0*10
        wcm_ptr_addr = self._resolver.resolve("WorldChrManPtrAddr").address
        wcm = self._mem.read_ptr(wcm_ptr_addr)
        if wcm == 0:
            raise PhantomError("WorldChrMan pointer is null")
        base10ef8 = self._mem.read_ptr(wcm + 0x10EF8)
        base_player0 = self._mem.read_ptr(base10ef8 + 0x0)
        base_flags = self._mem.read_ptr(self._mem.read_ptr(base_player0 + 0x190) + 0x0)

        if name in {"NoDead", "NoDamage", "NoFPConsumption", "NoStaminaConsumption"}:
            bit = int(bits.get(name))
            addr = base_flags + flag_base
            cur = self._mem.read_u8(addr) & 0xFF
            nxt = (cur | (1 << bit)) if enable else (cur & ~(1 << bit))
            self._mem.write_u8(addr, nxt)
            return

        if name == "NoGoodsConsume":
            addr = base_player0 + no_goods_base
            cur = self._mem.read_u8(addr) & 0xFF
            nxt = (cur | 0x01) if enable else (cur & ~0x01)
            self._mem.write_u8(addr, nxt)
            return

        if name == "NoArrowConsume":
            # From ER manager `cheats/no_goods.py`:
            # base_addr = base + 0x03DADAC0; arrow_addr = *(base_addr + 0x10); write u64 at (arrow_addr + 0x10)
            base_addr = self._mem.base_address + 0x03DADAC0
            arrow_addr = self._mem.read_ptr(base_addr + 0x10)
            if arrow_addr == 0:
                raise PhantomError("ArrowConsume pointer is null")
            target = arrow_addr + 0x10
            self._mem.write_u64(target, 256 if enable else 0)
            return

        if name == "NoHit":
            addr = base_player0 + no_hit_base
            cur = self._mem.read_u8(addr) & 0xFF
            nxt = (cur | (1 << 3)) if enable else (cur & ~(1 << 3))
            self._mem.write_u8(addr, nxt)
            return

        if name == "NoWeight":
            # Ported from internal cheat logic (pattern 5).
            module = self._mem.module("eldenring.exe")
            scanner = AOBScanner(self._mem)

            # Original bytes: FF C3 83 FB 05 (inc ebx; cmp ebx, 05)
            # Full sig includes context
            sig_orig = "FF C3 83 FB 05 7C CB 4C 8D 5C 24 70"
            sig_patched = "0F 57 F6 90 90 7C CB 4C 8D 5C 24 70"

            global _ER_NOWEIGHT_ORIG

            if enable:
                # Try to find original first
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_orig, symbol="ER_NoWeightPatch_Orig"
                    )
                    # Found original, save and patch
                    _ER_NOWEIGHT_ORIG[addr] = self._mem.read_bytes(addr, 5)
                    self._mem.write_bytes(addr, b"\x0f\x57\xf6\x90\x90")
                    return
                except PhantomError:
                    pass

                # Try to find patched (already enabled)
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="ER_NoWeightPatch_Patched"
                    )
                    # Already enabled, nothing to do
                    return
                except PhantomError:
                    raise PhantomError(
                        "Could not find NoWeight pattern (orig or patched)"
                    ) from None

            else:
                # Disable
                # Try to find patched first
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="ER_NoWeightPatch_Patched"
                    )
                    # Found patched, restore
                    # Prefer cached original bytes, else fallback to hardcoded (safe for this specific instruction)
                    orig = _ER_NOWEIGHT_ORIG.get(addr, b"\xff\xc3\x83\xfb\x05")
                    self._mem.write_bytes(addr, orig)
                    return
                except PhantomError:
                    pass

                # Try to find original (already disabled)
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_orig, symbol="ER_NoWeightPatch_Orig"
                    )
                    return
                except PhantomError:
                    raise PhantomError(
                        "Could not find NoWeight pattern (orig or patched)"
                    ) from None
            return

        raise PhantomError(f"Unsupported cheat for ER: {name}")

    def _set_ds3(self, name: str, enable: bool) -> None:
        # We replicate that behavior inside the FastAPI process.
        _ds3_runtime().set_enabled(name, enable)


class _Ds3CheatRuntime:
    """Background enforcer for DS3 cheats."""

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = False

        # Arrow patch bookkeeping (address -> original bytes)
        self._arrow_patch_addr: int | None = None
        self._arrow_patch_orig: bytes | None = None

    def set_enabled(self, cheat: str, enable: bool) -> None:
        # normalize
        if cheat.lower() == "noarrowconume":
            cheat = "NoArrowConsume"

        supported = {
            "NoDead",
            "NoDamage",
            "NoStaminaConsumption",
            "NoFPConsumption",
            "NoGoodsConsume",
            "NoHit",
            "NoArrowConsume",
            "NoWeight",
        }
        if cheat not in supported:
            raise PhantomError(f"Unsupported cheat for DS3: {cheat}")

        with self._lock:
            if enable:
                self._enabled.add(cheat)
            else:
                self._enabled.discard(cheat)

        # One-time patch toggles
        if cheat == "NoArrowConsume":
            self._apply_arrow_patch(enable)
        if cheat == "NoWeight":
            self._apply_no_weight_patch(enable)

        # Start the loop if any loop-based cheats enabled
        self._ensure_thread()

        # On disable, clear bits once (best-effort)
        if not enable and cheat != "NoArrowConsume":
            self._clear_once(cheat)

    def _ensure_thread(self) -> None:
        with self._lock:
            needs_loop = any(
                c in self._enabled
                for c in {
                    "NoDead",
                    "NoDamage",
                    "NoStaminaConsumption",
                    "NoFPConsumption",
                    "NoGoodsConsume",
                    "NoHit",
                }
            )
            if not needs_loop:
                return
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _apply_arrow_patch(self, enable: bool) -> None:
        # Based on internal DS3 cheat logic
        mem = None
        try:
            mem = MemoryClient("DarkSoulsIII.exe")
            # DS3 NoArrowConsume:
            # The original manager used: "89 51 08 C3 CC 7B 40"
            # On current DS3 build we verified the longer sequence below is UNIQUE.
            sig_tail = "7B 40 53 48 83 EC 30"
            sig_original = f"89 51 08 C3 CC {sig_tail}"
            sig_patched = f"90 90 90 C3 CC {sig_tail}"

            # Disable: restore bytes even if the server restarted and lost cached originals.
            if not enable:
                restore_bytes = b"\x89\x51\x08\xc3\xcc"
                if self._arrow_patch_addr is not None:
                    mem.write_bytes(self._arrow_patch_addr, restore_bytes)
                    return

                module = mem.module("DarkSoulsIII.exe")
                scanner = AOBScanner(mem)
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoArrowConsumePatch"
                    )
                    self._arrow_patch_addr = addr
                    mem.write_bytes(addr, restore_bytes)
                except Exception:
                    # Not patched (or signature changed) -> treat disable as idempotent success.
                    pass
                return

            # enable path: scan once, then cache address+original bytes
            module = mem.module("DarkSoulsIII.exe")
            scanner = AOBScanner(mem)
            try:
                addr = scanner.scan_module_unique(
                    module, sig_original, symbol="DS3_NoArrowConsumePatch"
                )
                self._arrow_patch_addr = addr
                mem.write_bytes(addr, b"\x90\x90\x90\xc3\xcc")
                return
            except Exception:
                # Already patched? Find patched signature and treat as enabled.
                addr = scanner.scan_module_unique(
                    module, sig_patched, symbol="DS3_NoArrowConsumePatch"
                )
                self._arrow_patch_addr = addr
                return
        except Exception as e:
            raise PhantomError(f"DS3 NoArrowConsume patch failed: {e}") from e
        finally:
            if mem:
                mem.close()

    def _apply_no_weight_patch(self, enable: bool) -> None:
        # Ported from internal DS3 cheat logic
        mem = None
        try:
            mem = MemoryClient("DarkSoulsIII.exe")
            module = mem.module("DarkSoulsIII.exe")
            scanner = AOBScanner(mem)

            sig_original = "F3 0F 58 F0 48 FF C7"
            sig_patched = "0F 57 F6 90 48 FF C7"

            # Disable: restore without scanning if we already know where.
            if not enable:
                if (
                    getattr(self, "_no_weight_addr", None) is not None
                    and getattr(self, "_no_weight_orig", None) is not None
                ):
                    mem.write_bytes(self._no_weight_addr, self._no_weight_orig)
                    return
                # Otherwise try to find the patched site and restore the original 4 bytes.
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoWeightPatch"
                    )
                    mem.write_bytes(addr, b"\xf3\x0f\x58\xf0")
                except Exception:
                    # Not patched or signature mismatch -> treat as idempotent.
                    pass
                return

            # Enable: find original site and patch
            addr = scanner.scan_module_unique(
                module, sig_original, symbol="DS3_NoWeightPatch"
            )
            if getattr(self, "_no_weight_addr", None) is None:
                self._no_weight_addr = addr
                self._no_weight_orig = mem.read_bytes(addr, 4)
            mem.write_bytes(addr, b"\x0f\x57\xf6\x90")
        except Exception as e:
            raise PhantomError(f"DS3 NoWeight patch failed: {e}") from e
        finally:
            if mem:
                mem.close()

    def _resolve_wcm(self, mem: MemoryClient) -> int:
        # Resolve via our configured AOB signature (WorldChrManPtrAddr points to global ptr).
        from phantom_backend.games.ds3.adapter import Ds3Adapter

        resolver = Ds3Adapter().make_resolver(mem)
        wcm_ptr_addr = resolver.resolve("WorldChrManPtrAddr").address
        return mem.read_ptr(wcm_ptr_addr)

    def _addr_flag_byte(self, mem: MemoryClient) -> int:
        # For NoDead/NoDamage/NoStamina/NoFP in your DS3 manager:
        # WorldChrMan > 0x80 -> * -> +0x1F90 -> * -> +0x18 -> * -> +0x1C0
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            raise PhantomError("WorldChrMan pointer is null")
        addr = mem.read_ptr(wcm + 0x80)
        addr = mem.read_ptr(addr + 0x1F90)
        addr = mem.read_ptr(addr + 0x18)
        return addr + 0x1C0

    def _addr_no_goods(self, mem: MemoryClient) -> int:
        # From internal DS3 cheat logic:
        # WorldChrMan > 0x80 -> * -> +0x1EEA, bit3
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            raise PhantomError("WorldChrMan pointer is null")
        addr = mem.read_ptr(wcm + 0x80)
        return addr + 0x1EEA

    def _addr_no_hit(self, mem: MemoryClient) -> int:
        # From internal DS3 cheat logic:
        # WorldChrMan > 0x80 -> * -> +0x1ED8, bit5
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            raise PhantomError("WorldChrMan pointer is null")
        addr = mem.read_ptr(wcm + 0x80)
        return addr + 0x1ED8

    def _set_bit(self, mem: MemoryClient, addr: int, bit: int, enable: bool) -> None:
        cur = mem.read_u8(addr) & 0xFF
        nxt = (cur | (1 << bit)) if enable else (cur & ~(1 << bit))
        mem.write_u8(addr, nxt)

    def _clear_once(self, cheat: str) -> None:
        mem = None
        try:
            mem = MemoryClient("DarkSoulsIII.exe")
            if cheat in {
                "NoDead",
                "NoDamage",
                "NoStaminaConsumption",
                "NoFPConsumption",
            }:
                addr = self._addr_flag_byte(mem)
                bit = {
                    "NoDamage": 1,
                    "NoDead": 2,
                    "NoStaminaConsumption": 4,
                    "NoFPConsumption": 5,
                }[cheat]
                self._set_bit(mem, addr, bit, False)
            elif cheat == "NoGoodsConsume":
                self._set_bit(mem, self._addr_no_goods(mem), 3, False)
            elif cheat == "NoHit":
                self._set_bit(mem, self._addr_no_hit(mem), 5, False)
        except Exception:
            pass
        finally:
            if mem:
                mem.close()

    def _loop(self) -> None:
        mem: MemoryClient | None = None
        while True:
            with self._lock:
                enabled = set(self._enabled)
                stop = self._stop
            if stop:
                break
            # If nothing needs looping, back off.
            if not (
                enabled
                & {
                    "NoDead",
                    "NoDamage",
                    "NoStaminaConsumption",
                    "NoFPConsumption",
                    "NoGoodsConsume",
                    "NoHit",
                }
            ):
                time.sleep(0.25)
                continue

            try:
                if mem is None:
                    mem = MemoryClient("DarkSoulsIII.exe")

                if enabled & {
                    "NoDead",
                    "NoDamage",
                    "NoStaminaConsumption",
                    "NoFPConsumption",
                }:
                    addr = self._addr_flag_byte(mem)
                    if "NoDamage" in enabled:
                        self._set_bit(mem, addr, 1, True)
                    if "NoDead" in enabled:
                        self._set_bit(mem, addr, 2, True)
                    if "NoStaminaConsumption" in enabled:
                        self._set_bit(mem, addr, 4, True)
                    if "NoFPConsumption" in enabled:
                        self._set_bit(mem, addr, 5, True)

                if "NoGoodsConsume" in enabled:
                    self._set_bit(mem, self._addr_no_goods(mem), 3, True)

                if "NoHit" in enabled:
                    self._set_bit(mem, self._addr_no_hit(mem), 5, True)

            except Exception:
                if mem:
                    mem.close()
                mem = None

            time.sleep(0.1)

        if mem:
            mem.close()


_DS3_RT: _Ds3CheatRuntime | None = None


def _ds3_runtime() -> _Ds3CheatRuntime:
    global _DS3_RT
    if _DS3_RT is None:
        _DS3_RT = _Ds3CheatRuntime()
    return _DS3_RT
