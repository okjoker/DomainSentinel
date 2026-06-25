"""Diff retrieval and on-demand computation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Diff, Scan, ScanStatus
from ..schemas import DiffOut, diff_to_out
from ..services import scanner
from ..storage import get_blob_store

router = APIRouter(prefix="/api", tags=["diffs"])


@router.get("/domains/{domain_id}/diffs", response_model=list[DiffOut])
async def list_domain_diffs(domain_id: int, session: AsyncSession = Depends(get_session)):
    diffs = (
        await session.execute(
            select(Diff).where(Diff.domain_id == domain_id).order_by(Diff.id.desc())
        )
    ).scalars().all()
    return [diff_to_out(d) for d in diffs]


@router.get("/domains/{domain_id}/diff/latest", response_model=DiffOut)
async def latest_domain_diff(domain_id: int, session: AsyncSession = Depends(get_session)):
    diff = (
        await session.execute(
            select(Diff).where(Diff.domain_id == domain_id).order_by(Diff.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if diff is None:
        raise HTTPException(status_code=404, detail="no diff yet for this domain")
    return diff_to_out(diff)


@router.post("/domains/{domain_id}/diff", response_model=DiffOut)
async def compute_domain_diff(
    domain_id: int,
    from_scan: int = Query(..., description="earlier scan id"),
    to_scan: int = Query(..., description="later scan id"),
    session: AsyncSession = Depends(get_session),
):
    earlier = await session.get(Scan, from_scan)
    later = await session.get(Scan, to_scan)
    for scan in (earlier, later):
        if scan is None or scan.domain_id != domain_id:
            raise HTTPException(status_code=404, detail="scan not found for this domain")
        if scan.status != ScanStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="both scans must be COMPLETED")
    diff = await scanner.compute_and_store_diff(session, earlier, later)
    await session.commit()
    return diff_to_out(diff)


@router.get("/diffs/{diff_id}", response_model=DiffOut)
async def get_diff(diff_id: int, session: AsyncSession = Depends(get_session)):
    diff = await session.get(Diff, diff_id)
    if diff is None:
        raise HTTPException(status_code=404, detail="diff not found")
    return diff_to_out(diff)


@router.get("/diffs/{diff_id}/screenshot")
async def get_diff_screenshot(diff_id: int, session: AsyncSession = Depends(get_session)):
    diff = await session.get(Diff, diff_id)
    if diff is None or not diff.screenshot_diff_key:
        raise HTTPException(status_code=404, detail="no screenshot diff available")
    data = await get_blob_store().get(diff.screenshot_diff_key)
    return Response(content=data, media_type="image/png")
