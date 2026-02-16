from __future__ import annotations

from fastapi import APIRouter

from phantom_backend.core.errors import (
    PatternNotFound,
    PatternNotUnique,
    PhantomError,
    SignatureNotFound,
)
from phantom_backend.games.registry import GameRegistry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/signatures/validate")
def validate_signatures(game: str):
    """Validate all configured symbols for a given game.

    Returns per-symbol: ok + resolved address or error type/message.
    """
    reg = GameRegistry()
    adapter = reg.get(game)
    mem = adapter.make_memory()
    try:
        resolver = adapter.make_resolver(mem)
        results = []
        for sym in adapter.required_symbols():
            try:
                resolved = resolver.resolve(sym)
                results.append(
                    {"symbol": sym, "ok": True, "address": hex(resolved.address)}
                )
            except (
                SignatureNotFound,
                PatternNotFound,
                PatternNotUnique,
                PhantomError,
            ) as e:
                results.append(
                    {
                        "symbol": sym,
                        "ok": False,
                        "error": {"type": e.__class__.__name__, "message": str(e)},
                    }
                )
        return {"game": game, "results": results}
    finally:
        mem.close()
