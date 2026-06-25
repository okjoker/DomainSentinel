"""Tests for the real Cloudflare client using mocked HTTP (respx)."""

import httpx
import pytest
import respx

from app.services.cloudflare import (
    CloudflareClient,
    CloudflareError,
    CloudflareRateLimited,
    ScanNotReady,
)

BASE = "https://api.cloudflare.com/client/v4/accounts/acc/urlscanner/v2"


def _client() -> CloudflareClient:
    return CloudflareClient(
        api_token="token",
        account_id="acc",
        api_base="https://api.cloudflare.com/client/v4",
    )


@respx.mock
async def test_create_scan_returns_uuid():
    route = respx.post(f"{BASE}/scan").mock(
        return_value=httpx.Response(200, json={"uuid": "abc123"})
    )
    client = _client()
    scan_id = await client.create_scan("https://example.com", ["desktop"])
    assert scan_id == "abc123"
    assert route.called
    sent = route.calls.last.request
    assert b"example.com" in sent.content
    await client.aclose()


@respx.mock
async def test_create_scan_rate_limited():
    respx.post(f"{BASE}/scan").mock(return_value=httpx.Response(429))
    client = _client()
    with pytest.raises(CloudflareRateLimited):
        await client.create_scan("https://example.com", ["desktop"])
    await client.aclose()


@respx.mock
async def test_create_scan_adopts_recent_scan_on_409():
    # Cloudflare dedups recent submissions ("website was recently scanned") and
    # returns the existing scan's uuid; we adopt it instead of failing.
    respx.post(f"{BASE}/scan").mock(
        return_value=httpx.Response(
            409,
            json={
                "message": "Submission unsuccessful: website was recently scanned",
                "status": 409,
                "result": {"tasks": [{"uuid": "existing-uuid"}]},
            },
        )
    )
    client = _client()
    scan_id = await client.create_scan("https://example.com", ["desktop"])
    assert scan_id == "existing-uuid"
    await client.aclose()


@respx.mock
async def test_create_scan_409_without_uuid_errors():
    respx.post(f"{BASE}/scan").mock(
        return_value=httpx.Response(409, json={"message": "recently scanned", "status": 409})
    )
    client = _client()
    with pytest.raises(CloudflareError):
        await client.create_scan("https://example.com", ["desktop"])
    await client.aclose()


@respx.mock
async def test_get_result_pending_then_ready():
    respx.get(f"{BASE}/result/abc").mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200, json={"page": {"title": "Hi"}}),
        ]
    )
    client = _client()
    with pytest.raises(ScanNotReady):
        await client.get_result("abc")
    result = await client.get_result("abc")
    assert result["page"]["title"] == "Hi"
    await client.aclose()


@respx.mock
async def test_get_result_unwraps_result_envelope():
    respx.get(f"{BASE}/result/abc").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"page": {"title": "Z"}}})
    )
    client = _client()
    result = await client.get_result("abc")
    assert result == {"page": {"title": "Z"}}
    await client.aclose()


@respx.mock
async def test_get_screenshot_bytes_and_missing():
    respx.get(f"{BASE}/screenshots/abc.png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG-bytes")
    )
    client = _client()
    assert await client.get_screenshot("abc") == b"\x89PNG-bytes"
    await client.aclose()

    respx.get(f"{BASE}/screenshots/missing.png").mock(return_value=httpx.Response(404))
    client = _client()
    assert await client.get_screenshot("missing") is None
    await client.aclose()
