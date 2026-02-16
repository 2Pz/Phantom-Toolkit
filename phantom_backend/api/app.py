from __future__ import annotations

import os
import traceback
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from phantom_backend.api.routes.actions import router as actions_router
from phantom_backend.api.routes.admin import router as admin_router
from phantom_backend.api.routes.backup import router as backup_router
from phantom_backend.api.routes.builds import router as builds_router
from phantom_backend.api.routes.cheats import router as cheats_router
from phantom_backend.api.routes.items import router as items_router
from phantom_backend.api.routes.players import router as players_router
from phantom_backend.api.routes.system import router as system_router
from phantom_backend.core.errors import PhantomError


def create_app() -> FastAPI:
    app = FastAPI(title="Phantom Backend", version="0.1.0")

    @app.on_event("startup")
    def on_startup():
        try:
            from phantom_backend.services import backup_service

            backup_service.initialize_hotkeys()
        except Exception:
            pass

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(players_router)
    app.include_router(items_router)
    app.include_router(cheats_router)
    app.include_router(actions_router)
    app.include_router(admin_router)
    app.include_router(system_router)
    app.include_router(builds_router)
    app.include_router(backup_router)

    # Put this last to avoid overriding API routes
    static_dir = os.environ.get("PHANTOM_STATIC_DIR")
    if static_dir and os.path.isdir(static_dir):
        # In packaged builds, missing static assets should not crash the server.
        # The SPA file route below can still serve files directly from `static_dir`
        # (including `/assets/...`) without needing an explicit StaticFiles mount.
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # If API route wasn't matched above, check if file exists in static dir
            # If not, serve index.html for SPA routing
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            # SPA Fallback
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
            return JSONResponse(status_code=404, content={"detail": "Not found"})

    def _log_error(title: str, exc: Exception) -> None:
        try:
            log_file = os.environ.get("PHANTOM_LOG_FILE", "error_log.txt")
            # Ensure directory exists if we fell back to default and it has a dir component
            log_path = os.path.abspath(log_file)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            with open(log_path, "a", encoding="utf-8") as f:
                import time

                timestamp = time.strftime("[%Y-%m-%d %H:%M:%S] ")
                f.write(f"{timestamp}{title}: {exc}\n")
                traceback.print_exc(file=f)
        except Exception:
            # Last resort fallback to stderr if logging fails
            traceback.print_exc()

    @app.exception_handler(PhantomError)
    def _phantom(_: Any, exc: PhantomError) -> JSONResponse:
        _log_error("PhantomError", exc)
        return JSONResponse(
            status_code=400,
            content={"error": {"type": exc.__class__.__name__, "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    def _unhandled(_: Any, exc: Exception) -> JSONResponse:
        _log_error("Unhandled Exception", exc)
        # Keep it simple in v1; once we add typed errors, we’ll map them explicitly.
        return JSONResponse(
            status_code=500,
            content={"error": {"type": exc.__class__.__name__, "message": str(exc)}},
        )

    return app


def run() -> None:
    host = os.getenv("PHANTOM_HOST", "127.0.0.1")
    port = int(os.getenv("PHANTOM_PORT", "8000"))
    uvicorn.run(
        "phantom_backend.api.app:create_app", host=host, port=port, factory=True
    )
