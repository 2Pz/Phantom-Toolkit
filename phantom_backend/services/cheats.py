from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from phantom_backend.core.aob import AOBScanner
from phantom_backend.core.errors import PhantomError
from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver
from phantom_backend.services.game_offsets import get_hex_int, load_manager_offsets


@dataclass(frozen=True)
class CheatInfo:
    name: str
    description: str


class BaseCheatRuntime(ABC):
    """Base class for background cheat enforcement."""

    def __init__(self, process_name: str, game_key: str):
        self._process_name = process_name
        self._game_key = game_key
        self._lock = threading.Lock()
        self._enabled: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = False
        self._resolver: Any = None
        self._last_mem_id: int | None = None

    def set_enabled(self, cheat: str, enable: bool) -> None:
        # Normalize name (handle common typos)
        if cheat.lower() == "noarrowconume":
            cheat = "NoArrowConsume"

        with self._lock:
            if enable:
                self._enabled.add(cheat)
            else:
                self._enabled.discard(cheat)

        # One-time patches or immediate cleanup
        try:
            self._on_toggle(cheat, enable)
        except Exception as e:
            # Re-raise so the API can report it, but ensure we don't break the background loop state
            raise PhantomError(f"Failed to toggle cheat {cheat}: {e}") from e

        # Ensure enforcer loop is running
        self._ensure_thread()

    def _ensure_thread(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(
                target=self._loop, name=f"CheatEnforcer-{self._game_key}", daemon=True
            )
            self._thread.start()

    def _loop(self) -> None:
        mem: MemoryClient | None = None
        while True:
            with self._lock:
                enabled = set(self._enabled)
                stop = self._stop
            if stop:
                break
            if not enabled:
                time.sleep(0.5)
                continue

            try:
                if mem is None:
                    mem = MemoryClient(self._process_name)

                # Track if memory client changed to invalidate resolver
                if self._last_mem_id != id(mem):
                    self._resolver = None
                    self._last_mem_id = id(mem)

                self._enforce(mem, enabled)
            except Exception:
                if mem:
                    mem.close()
                mem = None
                self._resolver = None
                self._last_mem_id = None
                time.sleep(1.0)  # Wait longer if game closed or error
                continue

            time.sleep(0.1)

        if mem:
            mem.close()

    @abstractmethod
    def _on_toggle(self, cheat: str, enable: bool) -> None:
        """Called when a cheat is toggled to apply one-time patches."""
        pass

    @abstractmethod
    def _enforce(self, mem: MemoryClient, enabled: set[str]) -> None:
        """Periodic enforcement of enabled cheats."""
        pass


class EldenRingCheatRuntime(BaseCheatRuntime):
    def __init__(self):
        super().__init__("eldenring.exe", "eldenring")
        self._noweight_orig: dict[int, bytes] = {}

    def _on_toggle(self, cheat: str, enable: bool) -> None:
        if cheat == "NoWeight":
            self._apply_no_weight(enable)
        elif not enable:
            self._clear_once(cheat)

    def _clear_once(self, cheat: str) -> None:
        mem = None
        try:
            mem = MemoryClient("eldenring.exe")
            self._write_cheat_state(mem, cheat, False)
        except Exception:
            pass
        finally:
            if mem:
                mem.close()

    def _apply_no_weight(self, enable: bool) -> None:
        # One-time AOB patch
        mem = None
        try:
            mem = MemoryClient("eldenring.exe")
            scanner = AOBScanner(mem)
            module = mem.module("eldenring.exe")

            sig_orig = "FF C3 83 FB 05 7C CB 4C 8D 5C 24 70"
            sig_patched = "0F 57 F6 90 90 7C CB 4C 8D 5C 24 70"

            if enable:
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_orig, symbol="ER_NoWeight_Orig"
                    )
                    self._noweight_orig[addr] = mem.read_bytes(addr, 5)
                    mem.write_bytes(addr, b"\x0f\x57\xf6\x90\x90")
                except Exception:
                    # If already patched, find the patched site to confirm it's enabled.
                    scanner.scan_module_unique(
                        module, sig_patched, symbol="ER_NoWeight_Patched"
                    )
            else:
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="ER_NoWeight_Patched"
                    )
                    orig = self._noweight_orig.get(addr, b"\xff\xc3\x83\xfb\x05")
                    mem.write_bytes(addr, orig)
                except Exception:
                    pass
        finally:
            if mem:
                mem.close()

    def _write_cheat_state(self, mem: MemoryClient, cheat: str, enable: bool) -> None:
        """Internal helper to write state for a single cheat (ER)."""
        from phantom_backend.games.eldenring.adapter import EldenRingAdapter

        # Use the loop's resolver if available and same mem
        resolver = self._resolver
        if resolver is None or id(mem) != self._last_mem_id:
            resolver = EldenRingAdapter().make_resolver(mem)

        try:
            wcm_ptr_addr = resolver.resolve("WorldChrManPtrAddr").address
            wcm = mem.read_ptr(wcm_ptr_addr)
            if wcm == 0:
                return
        except Exception:
            return

        cfg = load_manager_offsets("eldenring")
        bits = cfg.get("cheats", {}).get("bits", {})
        flag_base = get_hex_int(cfg, "cheats", "flag_base")
        no_goods_base = get_hex_int(cfg, "cheats", "no_goods_base")
        no_hit_base = get_hex_int(cfg, "cheats", "no_hit_base")

        base10ef8 = mem.read_ptr(wcm + 0x10EF8)
        if base10ef8 == 0:
            return
        base_player0 = mem.read_ptr(base10ef8 + 0x0)
        if base_player0 == 0:
            return

        if cheat in {"NoDead", "NoDamage", "NoFPConsumption", "NoStaminaConsumption"}:
            base_flags_ptr = mem.read_ptr(base_player0 + 0x190)
            if base_flags_ptr != 0:
                base_flags = mem.read_ptr(base_flags_ptr + 0x0)
                if base_flags != 0:
                    addr = base_flags + flag_base
                    bit = int(bits.get(cheat))
                    cur = mem.read_u8(addr)
                    nxt = (cur | (1 << bit)) if enable else (cur & ~(1 << bit))
                    if nxt != cur:
                        mem.write_u8(addr, nxt)

        elif cheat == "NoGoodsConsume":
            addr = base_player0 + no_goods_base
            cur = mem.read_u8(addr)
            nxt = (cur | 0x01) if enable else (cur & ~0x01)
            if nxt != cur:
                mem.write_u8(addr, nxt)

        elif cheat == "NoHit":
            addr = base_player0 + no_hit_base
            cur = mem.read_u8(addr)
            nxt = (cur | (1 << 3)) if enable else (cur & ~(1 << 3))
            if nxt != cur:
                mem.write_u8(addr, nxt)

        elif cheat == "NoArrowConsume":
            base_addr = mem.base_address + 0x03DADAC0
            try:
                arrow_addr = mem.read_ptr(base_addr + 0x10)
                if arrow_addr != 0:
                    target = arrow_addr + 0x10
                    val = 256 if enable else 0
                    if mem.read_u64(target) != val:
                        mem.write_u64(target, val)
            except Exception:
                pass

    def _enforce(self, mem: MemoryClient, enabled: set[str]) -> None:
        for cheat in enabled:
            self._write_cheat_state(mem, cheat, True)


class Ds3CheatRuntime(BaseCheatRuntime):
    def __init__(self):
        super().__init__("DarkSoulsIII.exe", "ds3")
        self._arrow_patch_addr: int | None = None
        self._no_weight_addr: int | None = None
        self._no_weight_orig: bytes | None = None

    def _on_toggle(self, cheat: str, enable: bool) -> None:
        if cheat == "NoArrowConsume":
            self._apply_arrow_patch(enable)
        if cheat == "NoWeight":
            self._apply_no_weight_patch(enable)

        # On disable, clear bits once (best-effort)
        if not enable and cheat not in {"NoArrowConsume", "NoWeight"}:
            self._clear_once(cheat)

    def _apply_arrow_patch(self, enable: bool) -> None:
        mem = None
        try:
            mem = MemoryClient("DarkSoulsIII.exe")
            sig_tail = "7B 40 53 48 83 EC 30"
            sig_original = f"89 51 08 C3 CC {sig_tail}"
            sig_patched = f"90 90 90 C3 CC {sig_tail}"

            if not enable:
                restore_bytes = b"\x89\x51\x08\xc3\xcc"
                if self._arrow_patch_addr is not None:
                    mem.write_bytes(self._arrow_patch_addr, restore_bytes)
                    return
                module = mem.module("DarkSoulsIII.exe")
                scanner = AOBScanner(mem)
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoArrow_Patched"
                    )
                    self._arrow_patch_addr = addr
                    mem.write_bytes(addr, restore_bytes)
                except Exception:
                    pass
                return

            module = mem.module("DarkSoulsIII.exe")
            scanner = AOBScanner(mem)
            try:
                addr = scanner.scan_module_unique(
                    module, sig_original, symbol="DS3_NoArrow_Orig"
                )
                self._arrow_patch_addr = addr
                mem.write_bytes(addr, b"\x90\x90\x90\xc3\xcc")
            except Exception:
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoArrow_Patched"
                    )
                    self._arrow_patch_addr = addr
                except Exception:
                    pass
        finally:
            if mem:
                mem.close()

    def _apply_no_weight_patch(self, enable: bool) -> None:
        mem = None
        try:
            mem = MemoryClient("DarkSoulsIII.exe")
            module = mem.module("DarkSoulsIII.exe")
            scanner = AOBScanner(mem)

            sig_original = "F3 0F 58 F0 48 FF C7"
            sig_patched = "0F 57 F6 90 48 FF C7"

            if not enable:
                if (
                    self._no_weight_addr is not None
                    and self._no_weight_orig is not None
                ):
                    mem.write_bytes(self._no_weight_addr, self._no_weight_orig)
                    return
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoWeight_Patched"
                    )
                    mem.write_bytes(addr, b"\xf3\x0f\x58\xf0")
                except Exception:
                    pass
                return

            try:
                addr = scanner.scan_module_unique(
                    module, sig_original, symbol="DS3_NoWeight_Orig"
                )
                self._no_weight_addr = addr
                self._no_weight_orig = mem.read_bytes(addr, 4)
                mem.write_bytes(addr, b"\x0f\x57\xf6\x90")
            except Exception:
                try:
                    addr = scanner.scan_module_unique(
                        module, sig_patched, symbol="DS3_NoWeight_Patched"
                    )
                    self._no_weight_addr = addr
                except Exception:
                    pass
        finally:
            if mem:
                mem.close()

    def _resolve_wcm(self, mem: MemoryClient) -> int:
        from phantom_backend.games.ds3.adapter import Ds3Adapter

        if self._resolver is None:
            self._resolver = Ds3Adapter().make_resolver(mem)

        wcm_ptr_addr = self._resolver.resolve("WorldChrManPtrAddr").address
        return mem.read_ptr(wcm_ptr_addr)

    def _addr_flag_byte(self, mem: MemoryClient) -> int:
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            return 0
        addr = mem.read_ptr(wcm + 0x80)
        if addr == 0:
            return 0
        addr = mem.read_ptr(addr + 0x1F90)
        if addr == 0:
            return 0
        addr = mem.read_ptr(addr + 0x18)
        if addr == 0:
            return 0
        return addr + 0x1C0

    def _addr_no_goods(self, mem: MemoryClient) -> int:
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            return 0
        addr = mem.read_ptr(wcm + 0x80)
        if addr == 0:
            return 0
        return addr + 0x1EEA

    def _addr_no_hit(self, mem: MemoryClient) -> int:
        wcm = self._resolve_wcm(mem)
        if wcm == 0:
            return 0
        addr = mem.read_ptr(wcm + 0x80)
        if addr == 0:
            return 0
        return addr + 0x1ED8

    def _set_bit(self, mem: MemoryClient, addr: int, bit: int, enable: bool) -> None:
        if addr == 0:
            return
        cur = mem.read_u8(addr)
        nxt = (cur | (1 << bit)) if enable else (cur & ~(1 << bit))
        if nxt != cur:
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

    def _enforce(self, mem: MemoryClient, enabled: set[str]) -> None:
        if enabled & {
            "NoDead",
            "NoDamage",
            "NoStaminaConsumption",
            "NoFPConsumption",
        }:
            addr = self._addr_flag_byte(mem)
            if addr != 0:
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


class CheatsService:
    """Unified Cheat Toggles with background enforcement."""

    def __init__(self, *, mem: MemoryClient, resolver: SymbolResolver, game_key: str):
        self._mem = mem
        self._resolver = resolver
        self._game = game_key

    def list_cheats(self) -> list[CheatInfo]:
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
        if name.lower() == "noarrowconume":
            name = "NoArrowConsume"

        if name not in {c.name for c in self.list_cheats()}:
            raise PhantomError(f"Unknown cheat: {name}")

        runtime = _get_runtime(self._game)
        runtime.set_enabled(name, enable)


_RUNTIMES: dict[str, BaseCheatRuntime] = {}


def _get_runtime(game_key: str) -> BaseCheatRuntime:
    if game_key not in _RUNTIMES:
        if game_key == "eldenring":
            _RUNTIMES[game_key] = EldenRingCheatRuntime()
        elif game_key == "ds3":
            _RUNTIMES[game_key] = Ds3CheatRuntime()
        else:
            raise PhantomError(f"Unsupported game: {game_key}")
    return _RUNTIMES[game_key]
