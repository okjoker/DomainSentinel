"""ORM models: Domain, Scan, Diff.

Datetimes are stored as naive UTC for consistent comparisons across SQLite and
Postgres (neither stores tz reliably in the same way); always use ``utcnow()``.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """Naive UTC timestamp."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ScanStatus(str, enum.Enum):
    QUEUED = "QUEUED"          # created, not yet submitted to Cloudflare
    SUBMITTED = "SUBMITTED"    # submitted, awaiting result (CF returns 404 until ready)
    FETCHING = "FETCHING"      # result ready, downloading artifacts
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_hours: Mapped[float] = mapped_column(Float, default=24.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    scans: Mapped[list["Scan"]] = relationship(
        back_populates="domain",
        cascade="all, delete-orphan",
        order_by="Scan.created_at",
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ScanStatus] = mapped_column(
        SAEnum(ScanStatus), default=ScanStatus.QUEUED, index=True
    )
    cf_scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Parsed highlights from the Cloudflare result JSON (full JSON kept in `result`).
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    verdict_malicious: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # BlobStore keys for the captured artifacts.
    screenshot_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dom_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    har_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    domain: Mapped["Domain"] = relationship(back_populates="scans")


class Diff(Base):
    __tablename__ = "diffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    from_scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    to_scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(16), default="none")  # none|low|medium|high
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    screenshot_diff_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
