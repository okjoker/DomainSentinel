"""Cloudflare URL Scanner v2 client.

Workflow (https://developers.cloudflare.com/radar/investigate/url-scanner/):
  1. POST   /accounts/{account_id}/urlscanner/v2/scan        -> returns scan uuid
  2. GET    /accounts/{account_id}/urlscanner/v2/result/{id} -> 404 until ready, then 200
  3. GET    /accounts/{account_id}/urlscanner/v2/screenshots/{id}.png?resolution=desktop
  4. GET    /accounts/{account_id}/urlscanner/v2/har/{id}
  5. GET    /accounts/{account_id}/urlscanner/v2/dom/{id}

``FakeCloudflareClient`` implements the same surface using synthetic artifacts so
the app runs with no credentials (local dev, demos, tests).
"""

from __future__ import annotations

import uuid as uuidlib
from functools import lru_cache
from typing import Protocol

import httpx

from ..config import get_settings
from . import synthetic


class CloudflareError(RuntimeError):
    """Unexpected error talking to the Cloudflare API."""


class ScanNotReady(Exception):
    """Raised when a scan result is requested before it is ready (HTTP 404)."""


class CloudflareRateLimited(Exception):
    """Raised on HTTP 429 from Cloudflare so the caller can retry later."""


class CloudflareScanner(Protocol):
    async def create_scan(self, url: str, screenshot_resolutions: list[str]) -> str: ...
    async def get_result(self, scan_id: str) -> dict: ...
    async def get_screenshot(self, scan_id: str, resolution: str = "desktop") -> bytes | None: ...
    async def get_har(self, scan_id: str) -> dict | None: ...
    async def get_dom(self, scan_id: str) -> str | None: ...
    async def aclose(self) -> None: ...


def _extract_uuid(data: dict) -> str:
    if isinstance(data, dict):
        if isinstance(data.get("uuid"), str):
            return data["uuid"]
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("uuid"), str):
            return result["uuid"]
    raise CloudflareError(f"could not find scan uuid in create response: {data!r}")


class CloudflareClient:
    def __init__(
        self,
        api_token: str,
        account_id: str,
        api_base: str,
        visibility: str = "Unlisted",
        timeout: float = 30.0,
    ) -> None:
        self._visibility = visibility
        base_url = f"{api_base.rstrip('/')}/accounts/{account_id}/urlscanner/v2"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout,
        )

    async def create_scan(self, url: str, screenshot_resolutions: list[str]) -> str:
        payload: dict = {"url": url, "visibility": self._visibility}
        if screenshot_resolutions:
            payload["screenshotsResolutions"] = screenshot_resolutions
        resp = await self._client.post("/scan", json=payload)
        if resp.status_code == 429:
            raise CloudflareRateLimited()
        if resp.status_code >= 400:
            raise CloudflareError(f"create_scan failed ({resp.status_code}): {resp.text[:300]}")
        return _extract_uuid(resp.json())

    async def get_result(self, scan_id: str) -> dict:
        resp = await self._client.get(f"/result/{scan_id}")
        if resp.status_code == 404:
            raise ScanNotReady()
        if resp.status_code == 429:
            raise CloudflareRateLimited()
        if resp.status_code >= 400:
            raise CloudflareError(f"get_result failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        # Some endpoints wrap the payload as {"success":..., "result": {...}}.
        if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
            return data["result"]
        return data

    async def get_screenshot(self, scan_id: str, resolution: str = "desktop") -> bytes | None:
        resp = await self._client.get(
            f"/screenshots/{scan_id}.png", params={"resolution": resolution}
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CloudflareError(f"get_screenshot failed ({resp.status_code})")
        return resp.content

    async def get_har(self, scan_id: str) -> dict | None:
        resp = await self._client.get(f"/har/{scan_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CloudflareError(f"get_har failed ({resp.status_code})")
        return resp.json()

    async def get_dom(self, scan_id: str) -> str | None:
        resp = await self._client.get(f"/dom/{scan_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CloudflareError(f"get_dom failed ({resp.status_code})")
        return resp.text

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeCloudflareClient:
    """Offline synthetic scanner. Results are immediately ready (no polling delay)."""

    def __init__(self) -> None:
        self._urls: dict[str, str] = {}

    async def create_scan(self, url: str, screenshot_resolutions: list[str]) -> str:
        scan_id = uuidlib.uuid4().hex
        self._urls[scan_id] = url
        return scan_id

    def _content(self, scan_id: str) -> dict:
        return synthetic.derive_content(self._urls.get(scan_id, ""), scan_id)

    async def get_result(self, scan_id: str) -> dict:
        return synthetic.make_result(self._content(scan_id), scan_id)

    async def get_screenshot(self, scan_id: str, resolution: str = "desktop") -> bytes | None:
        return synthetic.make_screenshot_png(self._content(scan_id))

    async def get_har(self, scan_id: str) -> dict | None:
        return synthetic.make_har(self._content(scan_id))

    async def get_dom(self, scan_id: str) -> str | None:
        return synthetic.make_dom_html(self._content(scan_id))

    async def aclose(self) -> None:  # nothing to close
        return None


@lru_cache
def get_cf_client() -> CloudflareScanner:
    settings = get_settings()
    if settings.use_fake_cloudflare:
        return FakeCloudflareClient()
    return CloudflareClient(
        api_token=settings.cf_api_token,
        account_id=settings.cf_account_id,
        api_base=settings.cf_api_base,
        visibility=settings.cf_visibility,
    )
