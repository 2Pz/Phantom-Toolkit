from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/builds", tags=["builds"])


class BuildFile(BaseModel):
    name: str
    path: str | None = None
    data: dict[str, Any]


@router.get("", response_model=list[str])
def list_builds():
    """List all saved build names."""
    # Deprecated: list_builds
    # We no longer strictly manage a builds directory.
    # Return empty list or scan current dir?
    # For now, return empty to avoid breaking API contract but effectively disabling the specific "saved_builds" view.
    return []


@router.get("/{name}", response_model=dict[str, Any])
def load_build(name: str):
    """Load a specific build."""
    # Deprecated: load_build by name (assumed in BUILDS_DIR)
    # Since we are moving to arbitrary paths, this is less useful.
    # We'll try to load from current directory if it exists, else 404.
    path = f"{name}.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Build not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("")
def save_build(build: BuildFile):
    """Save a build to a JSON file."""
    # If path is provided, use it. Otherwise fallback to name in current dir.
    if build.path:
        final_path = build.path
    else:
        # Fallback for legacy calls
        safe_name = "".join(
            c for c in build.name if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid build name")
        final_path = f"{safe_name}.json"

    try:
        with open(final_path, "w", encoding="utf-8") as f:
            json.dump(build.data, f, indent=2)
        return {"status": "ok", "path": final_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{name}")
def delete_build(name: str):
    """Delete a saved build."""
    # Deprecated/Dangerous without a restricted directory.
    # We will disable this to prevent arbitrary file deletion via API if name contains ..
    # Or just restrict to basename in cwd.

    # Safe path check
    if os.path.dirname(name):
        raise HTTPException(
            status_code=403,
            detail="Deleting files outside working directory is not allowed via this endpoint",
        )

    path = f"{name}.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Build not found")

    try:
        os.remove(path)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
