"""Async SQLAlchemy engine, session factory and schema bootstrap."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a SQLite file so the engine can open it."""
    marker = "sqlite+aiosqlite:///"
    if database_url.startswith(marker):
        raw_path = database_url[len(marker):]
        if raw_path and raw_path != ":memory:":
            Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


# Columns added after the initial release; create_all does not alter existing
# tables, so they are backfilled with ADD COLUMN (works on SQLite and Postgres).
_COLUMN_MIGRATIONS = [
    ("scans", "dns_records", "JSON"),
]


def _apply_column_migrations(conn) -> None:
    inspector = sa_inspect(conn)
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        if table in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


async def init_db() -> None:
    """Create tables if they do not exist (MVP; Alembic can replace this later)."""
    _ensure_sqlite_dir(_settings.database_url)
    from . import models  # noqa: F401  (register models on Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(_apply_column_migrations)
        await conn.run_sync(Base.metadata.create_all)
