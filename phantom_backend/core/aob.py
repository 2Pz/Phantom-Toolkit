from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import PatternNotFound, PatternNotUnique
from .memory import MemoryClient, ModuleInfo


def _parse_aob(pattern: str) -> list[int | None]:
    """Parses patterns like '48 8B ?? ?? 89' into bytes+wildcards."""
    parts = [p for p in pattern.strip().split() if p]
    out: list[int | None] = []
    for p in parts:
        if p in {"??", "?"}:
            out.append(None)
        else:
            out.append(int(p, 16))
    return out


def compile_aob_regex(pattern: str) -> re.Pattern[bytes]:
    tokens = _parse_aob(pattern)
    if not tokens:
        raise ValueError("Empty AOB pattern")

    chunks: list[bytes] = []
    for t in tokens:
        if t is None:
            chunks.append(b".")  # any byte
        else:
            chunks.append(re.escape(bytes([t])))
    return re.compile(b"".join(chunks), flags=re.DOTALL)


@dataclass(frozen=True)
class AobMatch:
    address: int


class AOBScanner:
    def __init__(self, mem: MemoryClient):
        self._mem = mem

    def scan_module(
        self, module: ModuleInfo, pattern: str, *, symbol: str
    ) -> list[AobMatch]:
        rx = compile_aob_regex(pattern)
        pat_len = len(_parse_aob(pattern))
        if pat_len <= 0:
            return []

        chunk_size = 1024 * 1024
        overlap = max(pat_len - 1, 0)

        matches: list[AobMatch] = []
        prev_tail = b""
        offset_in_module = 0

        while offset_in_module < module.size:
            read_size = min(chunk_size, module.size - offset_in_module)
            data = self._mem.read_bytes(module.base + offset_in_module, read_size)
            buf = prev_tail + data

            for m in rx.finditer(buf):
                addr = module.base + offset_in_module - len(prev_tail) + m.start()
                matches.append(AobMatch(address=addr))

            prev_tail = buf[-overlap:] if overlap else b""
            offset_in_module += read_size

        return matches

    def scan_module_unique(
        self, module: ModuleInfo, pattern: str, *, symbol: str
    ) -> int:
        matches = self.scan_module(module, pattern, symbol=symbol)
        if len(matches) == 0:
            raise PatternNotFound(symbol)
        if len(matches) != 1:
            raise PatternNotUnique(symbol, len(matches))
        return matches[0].address
