"""Domain ingest + management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import Diff, Domain, Scan
from ..schemas import (
    DomainCreate,
    DomainDetail,
    DomainSummary,
    DomainUpdate,
    diff_to_out,
    domain_to_out,
    scan_to_out,
)
from ..services import scanner

router = APIRouter(prefix="/api/domains", tags=["domains"])


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def _get_domain_or_404(session: AsyncSession, domain_id: int) -> Domain:
    domain = await session.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="domain not found")
    return domain


async def _domain_detail(session: AsyncSession, domain_id: int) -> DomainDetail:
    domain = await _get_domain_or_404(session, domain_id)
    scans = (
        await session.execute(
            select(Scan).where(Scan.domain_id == domain_id).order_by(Scan.id.desc())
        )
    ).scalars().all()
    latest_diff = (
        await session.execute(
            select(Diff).where(Diff.domain_id == domain_id).order_by(Diff.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return DomainDetail(
        **domain_to_out(domain).model_dump(),
        scans=[scan_to_out(s) for s in scans],
        latest_diff=diff_to_out(latest_diff) if latest_diff else None,
    )


@router.post("", response_model=DomainDetail, status_code=201)
async def create_domain(payload: DomainCreate, session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    domain = Domain(
        url=_normalize_url(payload.url),
        label=payload.label,
        interval_hours=payload.interval_hours or settings.default_scan_interval_hours,
        active=True,
    )
    session.add(domain)
    await session.flush()

    first_scan_id = None
    if payload.scan_now:
        scan = await scanner.create_and_queue_scan(session, domain)
        first_scan_id = scan.id
    await session.commit()

    if first_scan_id is not None:
        scanner.spawn_scan(first_scan_id)
    return await _domain_detail(session, domain.id)


@router.get("", response_model=list[DomainSummary])
async def list_domains(session: AsyncSession = Depends(get_session)):
    domains = (await session.execute(select(Domain).order_by(Domain.id))).scalars().all()
    summaries: list[DomainSummary] = []
    for domain in domains:
        scan_count = (
            await session.execute(
                select(func.count(Scan.id)).where(Scan.domain_id == domain.id)
            )
        ).scalar_one()
        last_scan = (
            await session.execute(
                select(Scan).where(Scan.domain_id == domain.id).order_by(Scan.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        last_diff = (
            await session.execute(
                select(Diff).where(Diff.domain_id == domain.id).order_by(Diff.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        summaries.append(
            DomainSummary(
                **domain_to_out(domain).model_dump(),
                scan_count=scan_count,
                last_scan_status=last_scan.status.value if last_scan else None,
                last_diff_severity=last_diff.severity if last_diff else None,
                last_diff_changed=last_diff.changed if last_diff else None,
            )
        )
    return summaries


@router.get("/{domain_id}", response_model=DomainDetail)
async def get_domain(domain_id: int, session: AsyncSession = Depends(get_session)):
    return await _domain_detail(session, domain_id)


@router.patch("/{domain_id}", response_model=DomainDetail)
async def update_domain(
    domain_id: int, payload: DomainUpdate, session: AsyncSession = Depends(get_session)
):
    domain = await _get_domain_or_404(session, domain_id)
    if payload.label is not None:
        domain.label = payload.label
    if payload.interval_hours is not None:
        domain.interval_hours = payload.interval_hours
    if payload.active is not None:
        domain.active = payload.active
    await session.commit()
    return await _domain_detail(session, domain_id)


@router.delete("/{domain_id}", status_code=204)
async def delete_domain(domain_id: int, session: AsyncSession = Depends(get_session)):
    domain = await _get_domain_or_404(session, domain_id)
    await session.delete(domain)
    await session.commit()


@router.post("/{domain_id}/scan", response_model=DomainDetail, status_code=202)
async def scan_domain(domain_id: int, session: AsyncSession = Depends(get_session)):
    domain = await _get_domain_or_404(session, domain_id)
    scan = await scanner.create_and_queue_scan(session, domain)
    await session.commit()
    scanner.spawn_scan(scan.id)
    return await _domain_detail(session, domain_id)
