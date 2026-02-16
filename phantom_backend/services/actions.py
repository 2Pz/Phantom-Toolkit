from __future__ import annotations

from phantom_backend.core.errors import PhantomError
from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver


class ActionsService:
    """Game actions (AOB-only)."""

    def __init__(self, *, mem: MemoryClient, resolver: SymbolResolver, game_key: str):
        self._mem = mem
        self._resolver = resolver
        self._game = game_key

    def quit_to_menu(self) -> None:
        # Derived from the existing managers' `utility/esc_menu.py`:
        # write a byte into the GameMan instance at a small fixed offset.
        sym = self._resolver.resolve("GameManPtrAddr")
        gm_ptr_addr = sym.address
        gm = self._mem.read_ptr(gm_ptr_addr)
        if gm == 0:
            raise PhantomError("GameMan pointer is null")

        if self._game == "eldenring":
            self._mem.write_u8(gm + 0x10, 1)
            return
        if self._game == "ds3":
            self._mem.write_u8(gm + 0x8, 1)
            return
        raise PhantomError(f"Unsupported game: {self._game}")

    def fogwall_anim(self, animation_id: int = 60060) -> None:
        # Derived from `utility/fog_wall_anim.py` in both managers:
        # follow a pointer chain from WorldChrMan and write the animation id.
        sym = self._resolver.resolve("WorldChrManPtrAddr")
        wcm_ptr_addr = sym.address
        wcm = self._mem.read_ptr(wcm_ptr_addr)
        if wcm == 0:
            raise PhantomError("WorldChrMan pointer is null")

        if self._game == "eldenring":
            # [[[[WorldChrMan]+1E508]+190]+58]+18
            addr = self._mem.read_ptr(wcm + 0x1E508)
            addr = self._mem.read_ptr(addr + 0x190)
            anim = self._mem.read_ptr(addr + 0x58) + 0x18
            self._mem.write_i32(anim, animation_id)
            return

        if self._game == "ds3":
            # WorldChrMan > 80 > 1F90 > 58 > 20
            addr = self._mem.read_ptr(wcm + 0x80)
            addr = self._mem.read_ptr(addr + 0x1F90)
            anim = self._mem.read_ptr(addr + 0x58) + 0x20
            self._mem.write_i32(anim, animation_id)
            return

        raise PhantomError(f"Unsupported game: {self._game}")

    def request_save(self) -> None:
        if self._game == "eldenring":
            # Derived from ER manager `tabs/save_backup_tab.py`:
            # write byte 1 to *(GameManPtr) + save_flag_offset from assets/offsets.toml
            from phantom_backend.services.game_offsets import (
                get_hex_int,
                load_manager_offsets,
            )

            cfg = load_manager_offsets("eldenring")
            save_flag_off = get_hex_int(cfg, "save_backup", "save_flag_offset")

            gm_ptr_addr = self._resolver.resolve("GameManPtrAddr").address
            gm = self._mem.read_ptr(gm_ptr_addr)
            if gm == 0:
                raise PhantomError("GameMan pointer is null")

            self._mem.write_u8(gm + save_flag_off, 1)
            return
        if self._game == "ds3":
            self._ds3_request_save_remote_thread()
            return
        raise PhantomError(f"Unsupported game: {self._game}")

    def _ds3_request_save_remote_thread(self) -> None:
        # DS3 approach: Create remote thread at SaveRequestThreadStart
        start_addr = self._resolver.resolve("SaveRequestThreadStart").address
        self._mem.start_thread(start_addr)

    def loading_fix_start(self) -> None:
        if self._game == "eldenring":
            base = self._mem.base_address

            # 1. Write initial params (SoloParamRepository?)
            # [base + 0x3D691D8]
            ptr1 = self._mem.read_ptr(base + 0x3D691D8)
            if ptr1:
                # write_bytes(pointer1 + 0x2C, 0, 0, 10, 11)
                self._mem.write_u8(ptr1 + 0x2C, 0)
                self._mem.write_u8(ptr1 + 0x2D, 0)
                self._mem.write_u8(ptr1 + 0x2E, 10)
                self._mem.write_u8(ptr1 + 0x2F, 11)

            # 2. Write to GameMan
            # [base + 0x3D69918] -> + 0xB60 = 11102950
            ptr2 = self._mem.read_ptr(base + 0x3D69918)
            if ptr2:
                self._mem.write_u32(ptr2 + 0xB60, 11102950)

            # 3. Aggressive Check & Warp
            # We try for a few seconds to detect the stuck state and warp if needed.
            # Unlike Seamless which runs a background thread indefinitely,
            # we will attempt this for a short burst (e.g. 5s) or just once.
            # Given the likely "I am stuck now" context, checking immediately and retrying briefly is safest.

            import time

            end_time = time.time() + 5.0
            warped = False

            while time.time() < end_time and not warped:
                if self._er_check_and_warp():
                    warped = True
                    break
                time.sleep(0.5)

            return

        if self._game == "ds3":
            # Placeholder for DS3 if needed
            return

        raise PhantomError(f"Unsupported game: {self._game}")

    def _er_check_and_warp(self) -> bool:
        """Mirror of Seamless LoadingFix.check_and_warp + lua_warp logic."""
        try:
            base = self._mem.base_address
            # Check multiplayer state first (safety)
            # mp_check = [base + 0x3D68448]
            mp_check = self._mem.read_ptr(base + 0x3D68448)
            if not mp_check:
                # If null, maybe not initialized, unsafe to warp
                return False

            mp_state = self._mem.read_u8(mp_check + 0x68)
            if mp_state != 0:
                # In multiplayer, unsafe to warp
                return False

            # Check loading stuck state
            # pointer1 same as mp_check? 3D68448
            # pointer2 = [pointer1 + 0x28]
            pointer2 = self._mem.read_ptr(mp_check + 0x28)
            # if byte at [pointer2 + 0x113] == 0 -> stuck/needs warp
            if self._mem.read_u8(pointer2 + 0x113) == 0:
                return self._er_lua_warp(11102950)
        except Exception:
            pass
        return False

    def _er_lua_warp(self, warp_id: int) -> bool:
        try:
            base = self._mem.base_address

            # m = [base + 0x3D67E48]
            m = self._mem.read_ptr(base + 0x3D67E48)
            if not m:
                return False

            # func_addr = [base + 0x3B31CD0]
            func_addr = self._mem.read_ptr(base + 0x3B31CD0)
            if not func_addr:
                return False

            arg1 = self._mem.read_ptr(m + 0x18)
            arg2 = self._mem.read_ptr(m + 0x08)
            arg3 = warp_id - 1000

            # Shellcode (x64)
            # sub rsp, 28
            shellcode = bytearray(
                [
                    0x48,
                    0x83,
                    0xEC,
                    0x28,  # sub rsp, 40 (0x28)
                    0x48,
                    0x89,
                    0x4C,
                    0x24,
                    0x20,  # mov [rsp+32], rcx
                    0x48,
                    0x89,
                    0x54,
                    0x24,
                    0x18,  # mov [rsp+24], rdx
                    0x4C,
                    0x89,
                    0x44,
                    0x24,
                    0x10,  # mov [rsp+16], r8
                    0x48,
                    0xB9,
                ]
            )  # mov rcx, arg1 ...
            shellcode.extend(arg1.to_bytes(8, "little"))
            shellcode.extend([0x48, 0xBA])  # mov rdx, arg2 ...
            shellcode.extend(arg2.to_bytes(8, "little"))
            shellcode.extend([0x49, 0xB8])  # mov r8, arg3 ...
            shellcode.extend(arg3.to_bytes(8, "little"))
            shellcode.extend([0x48, 0xB8])  # mov rax, func_addr ...
            shellcode.extend(func_addr.to_bytes(8, "little"))
            shellcode.extend(
                [
                    0xFF,
                    0xD0,  # call rax
                    0x48,
                    0x8B,
                    0x4C,
                    0x24,
                    0x20,  # mov rcx, [rsp+32]
                    0x48,
                    0x8B,
                    0x54,
                    0x24,
                    0x18,  # mov rdx, [rsp+24]
                    0x4C,
                    0x8B,
                    0x44,
                    0x24,
                    0x10,  # mov r8,  [rsp+16]
                    0x48,
                    0x83,
                    0xC4,
                    0x28,  # add rsp, 40
                    0xC3,  # ret
                ]
            )

            addr = self._mem.allocate(len(shellcode))
            self._mem.write_bytes(addr, bytes(shellcode))

            import time

            self._mem.start_thread(addr)
            # Wait briefly then free. In robust systems wait for object.
            # Using 100ms sleep as in Seamless impl
            time.sleep(0.1)
            self._mem.free(addr)

            return True
        except Exception:
            return False

    def loading_fix_stop(self) -> None:
        return
