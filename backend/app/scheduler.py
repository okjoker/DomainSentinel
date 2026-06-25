"""In-process APScheduler that periodically runs the scan lifecycle tick.

Used for local dev and single-instance deployments. In production you can set
``SCHEDULER_ENABLED=false`` and drive ``POST /api/cron/tick`` from Cloud Scheduler
instead (recommended when running multiple Cloud Run instances).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import get_settings
from .db import SessionLocal
from .services.scanner import tick

logger = logging.getLogger("domainsentinel.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_tick() -> None:
    try:
        async with SessionLocal() as session:
            summary = await tick(session)
        if any(summary.values()):
            logger.info("tick %s", summary)
    except Exception:  # noqa: BLE001 — never let a tick crash the scheduler
        logger.exception("scheduler tick failed")


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("in-process scheduler disabled (SCHEDULER_ENABLED=false)")
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_tick,
        trigger="interval",
        seconds=settings.scheduler_interval_seconds,
        id="scan-tick",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("scheduler started (interval=%ss)", settings.scheduler_interval_seconds)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
