from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .aob import AOBScanner
from .errors import PhantomError
from .memory import MemoryClient
from .signatures import SignatureStore


@dataclass(frozen=True)
class ResolvedSymbol:
    symbol: str
    address: int


class SymbolResolver:
    """Resolves named symbols via AOB signature scanning + offset adjustment.

    Important: AOB-only mode. If a signature is missing/empty, resolution fails.
    """

    def __init__(
        self,
        *,
        mem: MemoryClient,
        signature_toml: Path,
        default_module: str,
    ):
        self._mem = mem
        self._scanner = AOBScanner(mem)
        self._store = SignatureStore(signature_toml)
        self._default_module = default_module
        self._cache: dict[str, int] = {}

    def list_symbols(self) -> list[str]:
        return self._store.list_symbols()

    def resolve(self, symbol: str) -> ResolvedSymbol:
        if symbol in self._cache:
            return ResolvedSymbol(symbol=symbol, address=self._cache[symbol])

        sig = self._store.get(symbol)  # may raise SignatureNotFound
        module_name = sig.module or self._default_module
        module = self._mem.module(module_name)
        match_addr = self._scanner.scan_module_unique(
            module, sig.pattern, symbol=symbol
        )
        if sig.kind == "absolute":
            final_addr = match_addr + sig.offset
        elif sig.kind == "rip_relative":
            # Resolve instruction like: mov rax, [rip+rel32]
            # target = (match + rip_base_at) + *(int32 at match+rel32_at) + offset
            rel = self._mem.read_i32(match_addr + sig.rel32_at)
            base = match_addr + sig.rip_base_at
            final_addr = base + rel + sig.offset
        else:
            raise PhantomError(
                f"Unknown signature kind '{sig.kind}' for symbol '{symbol}'"
            )

        self._cache[symbol] = final_addr
        return ResolvedSymbol(symbol=symbol, address=final_addr)
