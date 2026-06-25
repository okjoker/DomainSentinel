"""Scan lifecycle: QUEUED -> SUBMITTED -> FETCHING -> COMPLETED | FAILED.

Cloudflare scanning is asynchronous, so a scan is advanced across several steps:
``submit_scan`` POSTs to Cloudflare; ``finalize_scan`` polls the result and, once
ready, downloads + stores artifacts and computes a diff against the previous
completed scan. ``tick`` is the idempotent driver used by both the in-process
scheduler and ``POST /api/cron/tick``; ``run_scan_now`` is the snappy
fire-and-forget path used for on-demand scans while the instance is warm.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import timedelta

from sqlalchemy import func, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Diff, Domain, Scan, ScanStatus, utcnow
from ..storage import get_blob_store
from .cloudflare import CloudflareRateLimited, ScanNotReady, get_cf_client
from .differ import ScanArtifacts, compute_diff, parse_highlights

logger = logging.getLogger("domainsentinel.scanner")

_ACTIVE_STATUSES = (ScanStatus.QUEUED, ScanStatus.SUBMITTED, ScanStatus.FETCHING)

# Keep strong references to fire-and-forget tasks so they are not garbage collected.
_background_tasks: set[asyncio.Task] = set()


def spawn_scan(scan_id: int) -> None:
    """Run ``run_scan_now`` in the background without blocking the request."""
    if not get_settings().autostart_scans:
        return
    task = asyncio.create_task(run_scan_now(scan_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _blob_key(domain_id: int, scan_id: int, name: str) -> str:
    return f"domains/{domain_id}/scans/{scan_id}/{name}"


async def create_and_queue_scan(session, domain: Domain) -> Scan:
    scan = Scan(domain_id=domain.id, status=ScanStatus.QUEUED)
    session.add(scan)
    await session.flush()
    return scan


async def submit_scan(session, scan: Scan, domain: Domain) -> bool:
    """QUEUED -> SUBMITTED. Returns True if submitted, False if it should be retried."""
    settings = get_settings()
    cf = get_cf_client()
    try:
        scan.cf_scan_id = await cf.create_scan(domain.url, settings.screenshot_resolution_list)
    except CloudflareRateLimited:
        logger.info("rate limited submitting scan %s; will retry", scan.id)
        return False
    except Exception as exc:  # noqa: BLE001 — record and move on
        scan.status = ScanStatus.FAILED
        scan.error = f"submit failed: {exc}"
        await session.flush()
        logger.warning("scan %s submit failed: %s", scan.id, exc)
        return False
    scan.status = ScanStatus.SUBMITTED
    scan.submitted_at = utcnow()
    await session.flush()
    return True


async def finalize_scan(session, scan: Scan, domain: Domain) -> bool:
    """SUBMITTED/FETCHING -> COMPLETED. Returns True when the scan reaches a terminal state."""
    settings = get_settings()
    cf = get_cf_client()
    blob = get_blob_store()

    try:
        result = await cf.get_result(scan.cf_scan_id)
    except ScanNotReady:
        if (
            scan.submitted_at
            and (utcnow() - scan.submitted_at).total_seconds() > settings.scan_poll_timeout_seconds
        ):
            scan.status = ScanStatus.FAILED
            scan.error = "timed out waiting for Cloudflare result"
            await session.flush()
            return True
        return False
    except CloudflareRateLimited:
        return False
    except Exception as exc:  # noqa: BLE001
        scan.status = ScanStatus.FAILED
        scan.error = f"result fetch failed: {exc}"
        await session.flush()
        return True

    scan.status = ScanStatus.FETCHING
    await session.flush()

    try:
        resolution = settings.screenshot_resolution_list[0]
        png = await cf.get_screenshot(scan.cf_scan_id, resolution)
        if png:
            key = _blob_key(domain.id, scan.id, "screenshot.png")
            await blob.put(key, png, "image/png")
            scan.screenshot_key = key
        dom = await cf.get_dom(scan.cf_scan_id)
        if dom is not None:
            key = _blob_key(domain.id, scan.id, "dom.html")
            await blob.put(key, dom.encode("utf-8"), "text/html")
            scan.dom_key = key
        har = await cf.get_har(scan.cf_scan_id)
        if har is not None:
            key = _blob_key(domain.id, scan.id, "har.json")
            await blob.put(key, json.dumps(har).encode("utf-8"), "application/json")
            scan.har_key = key
    except Exception as exc:  # noqa: BLE001
        scan.status = ScanStatus.FAILED
        scan.error = f"artifact download failed: {exc}"
        await session.flush()
        return True

    highlights = parse_highlights(result)
    scan.result = result
    scan.final_url = highlights["final_url"]
    scan.page_title = highlights["title"]
    scan.verdict_malicious = highlights["malicious"]
    scan.status = ScanStatus.COMPLETED
    scan.completed_at = utcnow()

    interval = domain.interval_hours or settings.default_scan_interval_hours
    domain.last_scan_at = utcnow()
    domain.next_scan_at = utcnow() + timedelta(hours=interval)
    await session.flush()

    previous = (
        await session.execute(
            select(Scan)
            .where(
                Scan.domain_id == domain.id,
                Scan.status == ScanStatus.COMPLETED,
                Scan.id < scan.id,
            )
            .order_by(Scan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if previous is not None:
        await compute_and_store_diff(session, previous, scan)
    await session.flush()
    return True


async def _load_artifacts(blob, scan: Scan) -> ScanArtifacts:
    dom = har = screenshot = None
    if scan.dom_key and await blob.exists(scan.dom_key):
        dom = (await blob.get(scan.dom_key)).decode("utf-8", "replace")
    if scan.har_key and await blob.exists(scan.har_key):
        har = json.loads(await blob.get(scan.har_key))
    if scan.screenshot_key and await blob.exists(scan.screenshot_key):
        screenshot = await blob.get(scan.screenshot_key)
    return ScanArtifacts(result=scan.result, dom=dom, har=har, screenshot=screenshot)


async def compute_and_store_diff(session, from_scan: Scan, to_scan: Scan) -> Diff:
    """Diff two completed scans and persist a Diff row (idempotent per scan pair)."""
    existing = (
        await session.execute(
            select(Diff).where(
                Diff.from_scan_id == from_scan.id, Diff.to_scan_id == to_scan.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    blob = get_blob_store()
    old = await _load_artifacts(blob, from_scan)
    new = await _load_artifacts(blob, to_scan)
    outcome = compute_diff(old, new)

    diff_key = None
    if outcome.screenshot_diff and outcome.summary.get("screenshot", {}).get("changed"):
        diff_key = (
            f"domains/{to_scan.domain_id}/diffs/{from_scan.id}_{to_scan.id}/screenshot_diff.png"
        )
        await blob.put(diff_key, outcome.screenshot_diff, "image/png")

    diff = Diff(
        domain_id=to_scan.domain_id,
        from_scan_id=from_scan.id,
        to_scan_id=to_scan.id,
        changed=outcome.changed,
        severity=outcome.severity,
        summary=outcome.summary,
        screenshot_diff_key=diff_key,
    )
    session.add(diff)
    await session.flush()
    return diff


async def tick(session) -> dict:
    """One scheduler/cron iteration: enqueue due rescans, submit, and finalize."""
    settings = get_settings()
    now = utcnow()
    summary = {"enqueued": 0, "submitted": 0, "finalized": 0, "pending": 0, "failed": 0}

    # 1. Enqueue scheduled rescans for due domains without an in-flight scan.
    due_domains = (
        await session.execute(
            select(Domain).where(
                Domain.active.is_(True),
                Domain.next_scan_at.is_not(None),
                Domain.next_scan_at <= now,
            )
        )
    ).scalars().all()
    for domain in due_domains:
        active_count = (
            await session.execute(
                select(func.count(Scan.id)).where(
                    Scan.domain_id == domain.id, Scan.status.in_(_ACTIVE_STATUSES)
                )
            )
        ).scalar_one()
        if active_count:
            continue
        await create_and_queue_scan(session, domain)
        interval = domain.interval_hours or settings.default_scan_interval_hours
        domain.next_scan_at = now + timedelta(hours=interval)
        summary["enqueued"] += 1
    await session.flush()

    # 2. Submit QUEUED scans.
    queued = (
        await session.execute(
            select(Scan).where(Scan.status == ScanStatus.QUEUED).order_by(Scan.id)
        )
    ).scalars().all()
    for scan in queued:
        domain = await session.get(Domain, scan.domain_id)
        if await submit_scan(session, scan, domain):
            summary["submitted"] += 1
        elif scan.status == ScanStatus.FAILED:
            summary["failed"] += 1

    # 3. Finalize in-flight scans.
    inflight = (
        await session.execute(
            select(Scan).where(Scan.status.in_((ScanStatus.SUBMITTED, ScanStatus.FETCHING)))
        )
    ).scalars().all()
    for scan in inflight:
        domain = await session.get(Domain, scan.domain_id)
        done = await finalize_scan(session, scan, domain)
        if done and scan.status == ScanStatus.COMPLETED:
            summary["finalized"] += 1
        elif scan.status == ScanStatus.FAILED:
            summary["failed"] += 1
        else:
            summary["pending"] += 1

    await session.commit()
    return summary


async def run_scan_now(scan_id: int) -> None:
    """Drive a single scan to completion (fire-and-forget for on-demand scans)."""
    settings = get_settings()

    async with SessionLocal() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            return
        domain = await session.get(Domain, scan.domain_id)
        if scan.status == ScanStatus.QUEUED:
            await submit_scan(session, scan, domain)
            await session.commit()
        if scan.status == ScanStatus.FAILED:
            return

    deadline = time.monotonic() + settings.scan_poll_timeout_seconds
    while time.monotonic() < deadline:
        async with SessionLocal() as session:
            scan = await session.get(Scan, scan_id)
            if scan is None or scan.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                return
            domain = await session.get(Domain, scan.domain_id)
            await finalize_scan(session, scan, domain)
            await session.commit()
            if scan.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                return
        await asyncio.sleep(settings.scan_poll_interval_seconds)
