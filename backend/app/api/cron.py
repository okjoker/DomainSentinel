"""Scheduled tick endpoint (driven by Cloud Scheduler in production)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..schemas import TickResult
from ..services import scanner

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/tick", response_model=TickResult)
async def cron_tick(request: Request, session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    if settings.cron_secret:
        if request.headers.get("X-Cron-Secret") != settings.cron_secret:
            raise HTTPException(status_code=403, detail="invalid or missing cron secret")
    summary = await scanner.tick(session)
    return TickResult(**summary)
