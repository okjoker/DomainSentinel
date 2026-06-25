"""Scan detail + artifact serving endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Scan
from ..schemas import ScanOut, scan_to_out
from ..storage import get_blob_store

router = APIRouter(prefix="/api/scans", tags=["scans"])


async def _get_scan_or_404(session: AsyncSession, scan_id: int) -> Scan:
    scan = await session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return scan


@router.get("/{scan_id}", response_model=ScanOut)
async def get_scan(scan_id: int, session: AsyncSession = Depends(get_session)):
    return scan_to_out(await _get_scan_or_404(session, scan_id))


@router.get("/{scan_id}/screenshot")
async def get_scan_screenshot(scan_id: int, session: AsyncSession = Depends(get_session)):
    scan = await _get_scan_or_404(session, scan_id)
    if not scan.screenshot_key:
        raise HTTPException(status_code=404, detail="no screenshot for this scan")
    data = await get_blob_store().get(scan.screenshot_key)
    return Response(content=data, media_type="image/png")


@router.get("/{scan_id}/dom")
async def get_scan_dom(scan_id: int, session: AsyncSession = Depends(get_session)):
    scan = await _get_scan_or_404(session, scan_id)
    if not scan.dom_key:
        raise HTTPException(status_code=404, detail="no DOM for this scan")
    data = await get_blob_store().get(scan.dom_key)
    # Served as text/plain so captured page scripts never execute from our origin.
    return Response(content=data, media_type="text/plain; charset=utf-8")


@router.get("/{scan_id}/har")
async def get_scan_har(scan_id: int, session: AsyncSession = Depends(get_session)):
    scan = await _get_scan_or_404(session, scan_id)
    if not scan.har_key:
        raise HTTPException(status_code=404, detail="no HAR for this scan")
    data = await get_blob_store().get(scan.har_key)
    return Response(content=data, media_type="application/json")
