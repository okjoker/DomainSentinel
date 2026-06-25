"""Pydantic request/response models and ORM-to-schema serializers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .models import Diff, Domain, Scan


# --------------------------------------------------------------------- requests


class DomainCreate(BaseModel):
    url: str = Field(..., description="URL or hostname to monitor")
    label: str | None = None
    interval_hours: float | None = Field(default=None, gt=0)
    scan_now: bool = True


class DomainUpdate(BaseModel):
    label: str | None = None
    interval_hours: float | None = Field(default=None, gt=0)
    active: bool | None = None


# -------------------------------------------------------------------- responses


class DomainOut(BaseModel):
    id: int
    url: str
    label: str | None
    active: bool
    interval_hours: float
    created_at: datetime
    last_scan_at: datetime | None
    next_scan_at: datetime | None


class ScanOut(BaseModel):
    id: int
    domain_id: int
    status: str
    cf_scan_id: str | None = None
    error: str | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    final_url: str | None = None
    page_title: str | None = None
    verdict_malicious: bool | None = None
    has_screenshot: bool = False
    has_dom: bool = False
    has_har: bool = False


class DiffOut(BaseModel):
    id: int
    domain_id: int
    from_scan_id: int
    to_scan_id: int
    created_at: datetime
    changed: bool
    severity: str
    summary: dict
    has_screenshot_diff: bool = False


class DomainSummary(DomainOut):
    scan_count: int = 0
    last_scan_status: str | None = None
    last_diff_severity: str | None = None
    last_diff_changed: bool | None = None


class DomainDetail(DomainOut):
    scans: list[ScanOut] = []
    latest_diff: DiffOut | None = None


class TickResult(BaseModel):
    enqueued: int = 0
    submitted: int = 0
    finalized: int = 0
    pending: int = 0
    failed: int = 0


# ------------------------------------------------------------------ serializers


def domain_to_out(domain: Domain) -> DomainOut:
    return DomainOut(
        id=domain.id,
        url=domain.url,
        label=domain.label,
        active=domain.active,
        interval_hours=domain.interval_hours,
        created_at=domain.created_at,
        last_scan_at=domain.last_scan_at,
        next_scan_at=domain.next_scan_at,
    )


def scan_to_out(scan: Scan) -> ScanOut:
    return ScanOut(
        id=scan.id,
        domain_id=scan.domain_id,
        status=scan.status.value,
        cf_scan_id=scan.cf_scan_id,
        error=scan.error,
        created_at=scan.created_at,
        submitted_at=scan.submitted_at,
        completed_at=scan.completed_at,
        final_url=scan.final_url,
        page_title=scan.page_title,
        verdict_malicious=scan.verdict_malicious,
        has_screenshot=scan.screenshot_key is not None,
        has_dom=scan.dom_key is not None,
        has_har=scan.har_key is not None,
    )


def diff_to_out(diff: Diff) -> DiffOut:
    return DiffOut(
        id=diff.id,
        domain_id=diff.domain_id,
        from_scan_id=diff.from_scan_id,
        to_scan_id=diff.to_scan_id,
        created_at=diff.created_at,
        changed=diff.changed,
        severity=diff.severity,
        summary=diff.summary or {},
        has_screenshot_diff=diff.screenshot_diff_key is not None,
    )
