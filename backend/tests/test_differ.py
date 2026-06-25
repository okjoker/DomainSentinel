"""Unit tests for the pure diff engine."""

import io

from PIL import Image

from app.services.differ import (
    ScanArtifacts,
    compute_diff,
    diff_dom,
    diff_har,
    diff_result,
    diff_screenshot,
    parse_highlights,
)


def _png(color, size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _har(hosts, status=200) -> dict:
    return {
        "log": {
            "entries": [
                {
                    "request": {"method": "GET", "url": f"https://{h}/"},
                    "response": {"status": status},
                }
                for h in hosts
            ]
        }
    }


# ------------------------------------------------------------------------- DOM


def test_diff_dom_detects_changes():
    old = "<html><body><h1>Hello</h1></body></html>"
    new = "<html><body><h1>Goodbye</h1><p>new</p></body></html>"
    result = diff_dom(old, new)
    assert result["available"] and result["changed"]
    assert result["added_count"] > 0 and result["removed_count"] > 0
    assert result["similarity"] < 1.0


def test_diff_dom_identical():
    html = "<html><body><h1>Same</h1></body></html>"
    result = diff_dom(html, html)
    assert result["available"] and not result["changed"]
    assert result["similarity"] == 1.0


def test_diff_dom_missing_artifact():
    assert diff_dom(None, "<html></html>")["available"] is False


# ------------------------------------------------------------------------- HAR


def test_diff_har_new_and_removed_hosts():
    result = diff_har(_har(["a.com", "b.com"]), _har(["b.com", "c.com"]))
    assert result["changed"]
    assert result["added_hosts"] == ["c.com"]
    assert result["removed_hosts"] == ["a.com"]


def test_diff_har_status_changes():
    result = diff_har(_har(["a.com"], status=200), _har(["a.com"], status=500))
    assert result["status_changes"] == [{"url": "https://a.com/", "from": 200, "to": 500}]


# ------------------------------------------------------------------ screenshot


def test_diff_screenshot_changed():
    summary, image = diff_screenshot(_png((255, 0, 0)), _png((0, 0, 255)))
    assert summary["available"] and summary["changed"]
    assert summary["changed_ratio"] > 0.5
    assert image is not None and image[:8] == b"\x89PNG\r\n\x1a\n"


def test_diff_screenshot_identical():
    same = _png((10, 20, 30))
    summary, _ = diff_screenshot(same, same)
    assert summary["available"] and not summary["changed"]
    assert summary["similarity"] == 1.0


# ---------------------------------------------------------------------- result


def test_parse_highlights():
    result = {
        "page": {"url": "https://x.com/", "title": "X"},
        "verdicts": {"overall": {"malicious": True, "categories": ["phishing"]}},
        "meta": {"processors": {"tech": {"data": [{"name": "nginx"}, {"name": "React"}]}}},
        "lists": {"domains": ["x.com", "cdn.x.com"], "ips": ["1.2.3.4"]},
    }
    highlights = parse_highlights(result)
    assert highlights["malicious"] is True
    assert highlights["title"] == "X"
    assert highlights["technologies"] == ["React", "nginx"]
    assert "phishing" in highlights["categories"]


def test_diff_result_verdict_and_tech():
    old = {"verdicts": {"overall": {"malicious": False}},
           "meta": {"processors": {"tech": {"data": [{"name": "nginx"}]}}}}
    new = {"verdicts": {"overall": {"malicious": True}},
           "meta": {"processors": {"tech": {"data": [{"name": "nginx"}, {"name": "Coinhive"}]}}}}
    result = diff_result(old, new)
    assert result["changed"]
    assert result["verdict_change"] == {"from": False, "to": True}
    assert result["technologies_added"] == ["Coinhive"]


# ------------------------------------------------------------------- aggregate


def test_compute_diff_high_severity_on_malicious():
    old = ScanArtifacts(result={"verdicts": {"overall": {"malicious": False}}})
    new = ScanArtifacts(result={"verdicts": {"overall": {"malicious": True}}})
    outcome = compute_diff(old, new)
    assert outcome.changed and outcome.severity == "high"
    assert "verdict_became_malicious" in outcome.summary["signals"]


def test_compute_diff_no_change():
    artifacts = ScanArtifacts(
        result={"verdicts": {"overall": {"malicious": False}}},
        dom="<html><body>same</body></html>",
        har=_har(["a.com"]),
    )
    other = ScanArtifacts(
        result={"verdicts": {"overall": {"malicious": False}}},
        dom="<html><body>same</body></html>",
        har=_har(["a.com"]),
    )
    outcome = compute_diff(artifacts, other)
    assert not outcome.changed and outcome.severity == "none"
