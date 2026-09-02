"""End-to-end API tests driven through the cron tick with the fake scanner."""


def _ingest(client, url="example.com"):
    resp = client.post("/api/domains", json={"url": url, "scan_now": False})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _scan_once(client, domain_id):
    assert client.post(f"/api/domains/{domain_id}/scan").status_code == 202
    # A single tick submits a QUEUED scan and finalizes it (fake results are instant).
    summary = client.post("/api/cron/tick").json()
    assert summary["failed"] == 0, summary


def test_health(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["fake_cloudflare"] is True


def test_ingest_normalizes_url(client):
    detail = client.post("/api/domains", json={"url": "example.org", "scan_now": False}).json()
    assert detail["url"] == "https://example.org"


def test_full_scan_and_diff_flow(client):
    domain_id = _ingest(client, "diffsite.test")
    _scan_once(client, domain_id)
    _scan_once(client, domain_id)

    detail = client.get(f"/api/domains/{domain_id}").json()
    completed = [s for s in detail["scans"] if s["status"] == "COMPLETED"]
    assert len(completed) == 2

    scans = sorted(completed, key=lambda s: s["id"])
    later = scans[1]
    assert later["has_screenshot"] and later["has_dom"] and later["has_har"]

    # DNS records are captured with every completed scan.
    dns = later["dns_records"]
    assert dns["available"] is True
    assert dns["ns"] and dns["mx"] and dns["spf"] and dns["dmarc"]

    # Artifacts are downloadable.
    assert client.get(f"/api/scans/{later['id']}/screenshot").headers["content-type"] == "image/png"
    assert client.get(f"/api/scans/{later['id']}/har").status_code == 200

    # A diff was auto-computed when the second scan completed.
    diff = client.get(f"/api/domains/{domain_id}/diff/latest").json()
    assert diff["from_scan_id"] == scans[0]["id"]
    assert diff["to_scan_id"] == later["id"]
    assert set(diff["summary"].keys()) >= {"screenshot", "dom", "har", "result", "dns", "signals"}
    assert diff["summary"]["dns"]["available"] is True


def test_optional_artifact_failure_does_not_fail_scan(client, monkeypatch):
    # A failing optional artifact (e.g. Cloudflare DOM 400) must not fail an
    # otherwise-good scan; the scan completes with whatever artifacts succeeded.
    from app.services.cloudflare import FakeCloudflareClient

    async def boom(self, scan_id):
        raise RuntimeError("dom 400")

    monkeypatch.setattr(FakeCloudflareClient, "get_dom", boom)

    domain_id = _ingest(client, "partial.test")
    assert client.post(f"/api/domains/{domain_id}/scan").status_code == 202
    summary = client.post("/api/cron/tick").json()
    assert summary["failed"] == 0, summary

    completed = [
        s for s in client.get(f"/api/domains/{domain_id}").json()["scans"]
        if s["status"] == "COMPLETED"
    ]
    assert len(completed) == 1
    scan = completed[0]
    assert scan["has_screenshot"] is True
    assert scan["has_har"] is True
    assert scan["has_dom"] is False  # the failed artifact was skipped, not fatal


def test_on_demand_diff_is_idempotent(client):
    domain_id = _ingest(client, "idem.test")
    _scan_once(client, domain_id)
    _scan_once(client, domain_id)
    scans = sorted(
        (s for s in client.get(f"/api/domains/{domain_id}").json()["scans"] if s["status"] == "COMPLETED"),
        key=lambda s: s["id"],
    )
    params = {"from_scan": scans[0]["id"], "to_scan": scans[1]["id"]}
    first = client.post(f"/api/domains/{domain_id}/diff", params=params).json()
    second = client.post(f"/api/domains/{domain_id}/diff", params=params).json()
    assert first["id"] == second["id"]


def test_delete_domain(client):
    domain_id = _ingest(client, "delete.test")
    assert client.delete(f"/api/domains/{domain_id}").status_code == 204
    assert client.get(f"/api/domains/{domain_id}").status_code == 404


def test_cron_secret_enforced(client):
    from app.config import get_settings

    settings = get_settings()
    settings.cron_secret = "s3cret"
    try:
        assert client.post("/api/cron/tick").status_code == 403
        assert client.post("/api/cron/tick", headers={"X-Cron-Secret": "wrong"}).status_code == 403
        ok = client.post("/api/cron/tick", headers={"X-Cron-Secret": "s3cret"})
        assert ok.status_code == 200
    finally:
        settings.cron_secret = ""
