"""FastAPI application: REST API + (optionally) the built SPA, in one container."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import cron, diffs, domains, scans
from .config import get_settings
from .db import init_db
from .scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("domainsentinel")


def _resolve_static_dir(settings) -> Path | None:
    if settings.static_dir:
        path = Path(settings.static_dir)
    else:
        path = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return path if path.exists() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    logger.info(
        "DomainSentinel %s started (fake_cloudflare=%s)",
        __version__,
        get_settings().use_fake_cloudflare,
    )
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DomainSentinel", version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(domains.router)
    app.include_router(scans.router)
    app.include_router(diffs.router)
    app.include_router(cron.router)

    @app.get("/healthz", tags=["meta"])
    async def healthz():
        return {
            "status": "ok",
            "version": __version__,
            "fake_cloudflare": settings.use_fake_cloudflare,
        }

    @app.get("/api/info", tags=["meta"])
    async def info():
        return {
            "version": __version__,
            "fake_cloudflare": settings.use_fake_cloudflare,
            "default_scan_interval_hours": settings.default_scan_interval_hours,
        }

    static_dir = _resolve_static_dir(settings)
    if static_dir is not None:
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            # API + health routes are matched earlier; never let them fall through to index.html.
            if full_path.startswith(("api/", "healthz")):
                raise HTTPException(status_code=404, detail="not found")
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

        logger.info("serving SPA from %s", static_dir)
    else:

        @app.get("/", include_in_schema=False)
        async def root():
            return {
                "app": "DomainSentinel",
                "docs": "/docs",
                "note": "SPA build not found; run the frontend dev server or build it.",
            }

    return app


app = create_app()
