from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from phantom_backend.core.memory import MemoryClient
from phantom_backend.core.resolver import SymbolResolver


@dataclass(frozen=True)
class GameInfo:
    key: str
    process_name: str
    module_name: str
    signatures_toml: Path


class GameAdapter(Protocol):
    info: GameInfo

    def make_memory(self) -> MemoryClient: ...

    def make_resolver(self, mem: MemoryClient) -> SymbolResolver: ...

    def required_symbols(self) -> list[str]: ...


class BaseGameAdapter:
    def __init__(
        self, key: str, process_name: str, module_name: str, signatures_toml: Path
    ):
        self.info = GameInfo(
            key=key,
            process_name=process_name,
            module_name=module_name,
            signatures_toml=signatures_toml,
        )

    def make_memory(self) -> MemoryClient:
        return MemoryClient(self.info.process_name)

    def make_resolver(self, mem: MemoryClient) -> SymbolResolver:
        return SymbolResolver(
            mem=mem,
            signature_toml=self.info.signatures_toml,
            default_module=self.info.module_name,
        )

    def required_symbols(self) -> list[str]:
        raise NotImplementedError
