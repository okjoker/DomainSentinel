"""Blob storage abstraction for scan artifacts (screenshots, DOM, HAR, diff images).

``LocalBlobStore`` writes to the filesystem (local-first default). ``GCSBlobStore``
talks to Google Cloud Storage and is selected by ``BLOB_BACKEND=gcs`` with no other
code changes. Keys are POSIX-style relative paths, e.g.
``domains/1/scans/3/screenshot.png``.
"""

from __future__ import annotations

import abc
import asyncio
from functools import lru_cache
from pathlib import Path

from ..config import get_settings

DEFAULT_CONTENT_TYPE = "application/octet-stream"


class BlobStore(abc.ABC):
    @abc.abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> str:
        """Store bytes under ``key`` and return the key."""

    @abc.abstractmethod
    async def get(self, key: str) -> bytes:
        """Return the stored bytes for ``key`` (raises if missing)."""

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        ...


class LocalBlobStore(BlobStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Guard against path traversal via crafted keys.
        if self.root not in path.parents and path != self.root:
            raise ValueError(f"invalid blob key: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> str:
        def _write() -> None:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)
        return key

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(lambda: self._path(key).read_bytes())

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(lambda: self._path(key).exists())

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            path = self._path(key)
            if path.exists():
                path.unlink()

        await asyncio.to_thread(_delete)


class GCSBlobStore(BlobStore):
    """Google Cloud Storage backend. Requires ``google-cloud-storage`` (requirements-gcp.txt)."""

    def __init__(self, bucket: str, prefix: str = "") -> None:
        from google.cloud import storage  # lazy import; only needed in GCS mode

        if not bucket:
            raise ValueError("GCS_BUCKET must be set when BLOB_BACKEND=gcs")
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix.strip("/")

    def _name(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    async def put(self, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> str:
        def _upload() -> None:
            blob = self._bucket.blob(self._name(key))
            blob.upload_from_string(data, content_type=content_type)

        await asyncio.to_thread(_upload)
        return key

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(
            lambda: self._bucket.blob(self._name(key)).download_as_bytes()
        )

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(lambda: self._bucket.blob(self._name(key)).exists())

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            blob = self._bucket.blob(self._name(key))
            if blob.exists():
                blob.delete()

        await asyncio.to_thread(_delete)


@lru_cache
def get_blob_store() -> BlobStore:
    settings = get_settings()
    if settings.blob_backend.lower() == "gcs":
        return GCSBlobStore(settings.gcs_bucket, settings.gcs_prefix)
    return LocalBlobStore(settings.blob_local_dir)
