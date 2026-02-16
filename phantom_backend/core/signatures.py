from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import SignatureConfigError, SignatureNotFound


@dataclass(frozen=True)
class Signature:
    symbol: str
    pattern: str
    offset: int
    module: str | None = None
    kind: str = "absolute"  # "absolute" | "rip_relative"
    rel32_at: int = 3  # only for rip_relative
    rip_base_at: int = 7  # only for rip_relative


def _parse_offset(text: str) -> int:
    t = text.strip().lower()
    sign = 1
    if t.startswith("+"):
        t = t[1:].strip()
    if t.startswith("-"):
        sign = -1
        t = t[1:].strip()
    if not t.startswith("0x"):
        raise SignatureConfigError(
            f"Offset must be hex like 0x10 or -0x10, got: {text}"
        )
    return sign * int(t, 16)


class SignatureStore:
    def __init__(self, toml_path: Path):
        self.toml_path = toml_path
        self._data = self._load()

    def _load(self) -> dict:
        if not self.toml_path.exists():
            raise SignatureConfigError(f"Signature TOML not found: {self.toml_path}")
        raw = self.toml_path.read_bytes()
        return tomllib.loads(raw.decode("utf-8"))

    def get(self, symbol: str) -> Signature:
        symbols = self._data.get("symbols", {})
        entry = symbols.get(symbol)
        if not entry:
            raise SignatureNotFound(symbol)
        pattern = entry.get("pattern")
        if not pattern or not str(pattern).strip():
            raise SignatureNotFound(symbol)
        offset = _parse_offset(str(entry.get("offset", "0x0")))
        module = entry.get("module")
        kind = str(entry.get("kind", "absolute")).strip().lower()
        rel32_at = int(entry.get("rel32_at", 3))
        rip_base_at = int(entry.get("rip_base_at", 7))
        return Signature(
            symbol=symbol,
            pattern=str(pattern),
            offset=offset,
            module=str(module) if module else None,
            kind=kind,
            rel32_at=rel32_at,
            rip_base_at=rip_base_at,
        )

    def list_symbols(self) -> list[str]:
        symbols = self._data.get("symbols", {})
        return sorted(str(k) for k in symbols)
