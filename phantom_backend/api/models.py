from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerSummary(BaseModel):
    player_num: int
    name: str
    level: int


class PlayerDetails(BaseModel):
    player_num: int
    is_valid: bool
    name: str = ""
    level: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)
    equipment: dict[str, Any] = Field(default_factory=dict)


class WriteStatsRequest(BaseModel):
    stats: dict[str, Any]


class WriteBuildRequest(BaseModel):
    equipment: dict[str, Any]
    stats: dict[str, Any] | None = None
    shadow_of_erdtree: dict[str, Any] | None = None
    quantities: dict[str, Any] | None = None
