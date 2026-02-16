import contextlib
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .errors import ModuleNotFound, PhantomError, ProcessNotFound

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import pymem
    import pymem.process


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    base: int
    size: int


class MemoryBackend(ABC):
    """Abstract base class for platform-specific memory backends."""

    def __init__(self, process_name: str):
        self.process_name = process_name

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def get_handle(self) -> int: ...

    @abstractmethod
    def get_base_address(self) -> int: ...

    @abstractmethod
    def module(self, module_name: str) -> ModuleInfo: ...

    @abstractmethod
    def read_bytes(self, address: int, size: int) -> bytes: ...

    @abstractmethod
    def write_bytes(self, address: int, data: bytes) -> None: ...

    @abstractmethod
    def allocate(self, size: int) -> int: ...

    @abstractmethod
    def free(self, address: int) -> None: ...

    @abstractmethod
    def start_thread(self, address: int) -> int: ...


class WindowsMemoryBackend(MemoryBackend):
    def __init__(self, process_name: str):
        super().__init__(process_name)
        try:
            self._pm = pymem.Pymem(process_name)
        except Exception as e:
            raise ProcessNotFound(process_name) from e

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pm.close_process()

    def get_handle(self) -> int:
        return self._pm.process_handle

    def get_base_address(self) -> int:
        return self._pm.base_address

    def module(self, module_name: str) -> ModuleInfo:
        mod = pymem.process.module_from_name(self._pm.process_handle, module_name)
        if not mod:
            raise ModuleNotFound(module_name)
        return ModuleInfo(name=module_name, base=mod.lpBaseOfDll, size=mod.SizeOfImage)

    def read_bytes(self, address: int, size: int) -> bytes:
        return self._pm.read_bytes(address, size)

    def write_bytes(self, address: int, data: bytes) -> None:
        self._pm.write_bytes(address, data, len(data))

    def allocate(self, size: int) -> int:
        return self._pm.allocate(size)

    def free(self, address: int) -> None:
        self._pm.free(address)

    def start_thread(self, address: int) -> int:
        h = self._pm.start_thread(address)
        import ctypes

        ctypes.windll.kernel32.WaitForSingleObject(h, 0xFFFFFFFF)
        ctypes.windll.kernel32.CloseHandle(h)
        return 0


class MemoryClient:
    """Unified cross-platform memory client."""

    def __init__(self, process_name: str):
        if not IS_WINDOWS:
            raise PhantomError(
                "Native Linux memory writing is disabled.\n\n"
                "Run the Windows build (PhantomToolkit.exe) through Steam Proton so we can use pymem.\n\n"
                "Options:\n"
                "- Use the Proton AppImage wrapper (PhantomToolkit-Proton-*.AppImage), or\n"
                "- Run: scripts/run_proton_phantomtoolkit.sh --exe /path/to/PhantomToolkit.exe\n"
                "- If you're using the native Linux desktop build, place PhantomToolkit.exe next to it\n"
                "  (or set PHANTOM_WINDOWS_EXE) and it will auto-launch via Proton by default."
            )

        self._backend = WindowsMemoryBackend(process_name)

        self.process_name = process_name
        self.process_handle = self._backend.get_handle()
        self.base_address = self._backend.get_base_address()

    def close(self) -> None:
        self._backend.close()

    def module(self, module_name: str) -> ModuleInfo:
        return self._backend.module(module_name)

    def read_bytes(self, address: int, size: int) -> bytes:
        return self._backend.read_bytes(address, size)

    def write_bytes(self, address: int, data: bytes) -> None:
        self._backend.write_bytes(address, data)

    def read_u8(self, address: int) -> int:
        data = self.read_bytes(address, 1)
        return data[0] if data else 0

    def write_u8(self, address: int, value: int) -> None:
        self.write_bytes(address, bytes([value & 0xFF]))

    def read_u16(self, address: int) -> int:
        import struct

        data = self.read_bytes(address, 2)
        return struct.unpack("<H", data)[0] if len(data) == 2 else 0

    def write_u16(self, address: int, value: int) -> None:
        import struct

        self.write_bytes(address, struct.pack("<H", value))

    def read_u32(self, address: int) -> int:
        import struct

        data = self.read_bytes(address, 4)
        return struct.unpack("<I", data)[0] if len(data) == 4 else 0

    def write_u32(self, address: int, value: int) -> None:
        import struct

        self.write_bytes(address, struct.pack("<I", value))

    def read_i32(self, address: int) -> int:
        import struct

        data = self.read_bytes(address, 4)
        return struct.unpack("<i", data)[0] if len(data) == 4 else 0

    def write_i32(self, address: int, value: int) -> None:
        import struct

        self.write_bytes(address, struct.pack("<i", value))

    def read_u64(self, address: int) -> int:
        import struct

        data = self.read_bytes(address, 8)
        return struct.unpack("<Q", data)[0] if len(data) == 8 else 0

    def write_u64(self, address: int, value: int) -> None:
        import struct

        self.write_bytes(address, struct.pack("<Q", value))

    def read_ptr(self, address: int) -> int:
        return self.read_u64(address)

    def resolve_ptr_chain(self, base: int, offsets: list[int]) -> int | None:
        try:
            addr = base
            for off in offsets:
                addr = self.read_ptr(addr) + off
            return addr
        except Exception:
            return None

    def allocate(self, size: int) -> int:
        return self._backend.allocate(size)

    def free(self, address: int) -> None:
        self._backend.free(address)

    def start_thread(self, address: int) -> int:
        return self._backend.start_thread(address)
