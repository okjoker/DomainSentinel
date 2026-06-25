"""Diff engine: compares two scans of the same domain across four dimensions.

  * screenshot  – pixel/visual difference + a red-tinted overlay highlighting changes
  * dom         – normalized HTML line diff (added/removed/unified)
  * har         – network changes: new/removed hosts, requests, status codes
  * result      – verdict, threat categories, technologies, final URL, IPs

Each dimension contributes severity signals; the overall severity is the max
(none < low < medium < high). All inputs are plain artifacts (dict/str/bytes) so
the engine is pure and easily unit-tested.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageStat

# Pixels with a grayscale delta below this are treated as unchanged (anti-aliasing noise).
_PIXEL_THRESHOLD = 16
_SEVERITY_NAMES = {0: "none", 1: "low", 2: "medium", 3: "high"}


@dataclass
class ScanArtifacts:
    result: dict | None = None
    dom: str | None = None
    har: dict | None = None
    screenshot: bytes | None = None


@dataclass
class DiffOutcome:
    changed: bool
    severity: str
    summary: dict = field(default_factory=dict)
    screenshot_diff: bytes | None = None


def parse_highlights(result: dict | None) -> dict:
    """Pull the fields DomainSentinel cares about out of a Cloudflare result JSON."""
    result = result or {}
    page = result.get("page") or {}
    task = result.get("task") or {}
    overall = (result.get("verdicts") or {}).get("overall") or {}
    tech_data = (
        ((result.get("meta") or {}).get("processors") or {}).get("tech") or {}
    ).get("data") or []
    lists = result.get("lists") or {}

    technologies = sorted(
        {t.get("name") for t in tech_data if isinstance(t, dict) and t.get("name")}
    )
    malicious = overall.get("malicious")
    return {
        "final_url": page.get("url") or task.get("url"),
        "title": page.get("title"),
        "malicious": bool(malicious) if malicious is not None else None,
        "categories": sorted(overall.get("categories") or []),
        "technologies": technologies,
        "domains": sorted(d for d in (lists.get("domains") or []) if d),
        "ips": sorted(i for i in (lists.get("ips") or []) if i),
    }


# --------------------------------------------------------------------------- DOM


def _normalize_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [line.rstrip() for line in soup.prettify().splitlines() if line.strip()]


def diff_dom(old_html: str | None, new_html: str | None) -> dict:
    if old_html is None or new_html is None:
        return {"available": False, "changed": False}
    old_lines = _normalize_html(old_html)
    new_lines = _normalize_html(new_html)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(old_lines[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(new_lines[j1:j2])
    unified = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=2))
    return {
        "available": True,
        "changed": bool(added or removed),
        "similarity": round(matcher.ratio(), 4),
        "added_count": len(added),
        "removed_count": len(removed),
        "added_lines": added[:200],
        "removed_lines": removed[:200],
        "unified": unified[:400],
    }


# --------------------------------------------------------------------------- HAR


def _har_entries(har: dict | None) -> list[dict]:
    if not isinstance(har, dict):
        return []
    log = har.get("log") if "log" in har else har
    entries = (log or {}).get("entries") or []
    parsed = []
    for entry in entries:
        request = entry.get("request") or {}
        response = entry.get("response") or {}
        url = request.get("url") or ""
        parsed.append(
            {
                "url": url,
                "host": urlparse(url).netloc,
                "method": request.get("method"),
                "status": response.get("status"),
                "type": entry.get("_resourceType") or entry.get("type"),
            }
        )
    return parsed


def diff_har(old_har: dict | None, new_har: dict | None) -> dict:
    if old_har is None or new_har is None:
        return {"available": False, "changed": False}
    old = _har_entries(old_har)
    new = _har_entries(new_har)
    old_hosts = {e["host"] for e in old if e["host"]}
    new_hosts = {e["host"] for e in new if e["host"]}
    old_urls = {e["url"] for e in old if e["url"]}
    new_urls = {e["url"] for e in new if e["url"]}

    old_status = {e["url"]: e["status"] for e in old if e["url"]}
    status_changes = [
        {"url": e["url"], "from": old_status[e["url"]], "to": e["status"]}
        for e in new
        if e["url"] in old_status and old_status[e["url"]] != e["status"]
    ]

    added_hosts = sorted(new_hosts - old_hosts)
    removed_hosts = sorted(old_hosts - new_hosts)
    added_requests = sorted(new_urls - old_urls)
    removed_requests = sorted(old_urls - new_urls)
    changed = bool(
        added_hosts or removed_hosts or added_requests or removed_requests or status_changes
    )
    return {
        "available": True,
        "changed": changed,
        "added_hosts": added_hosts,
        "removed_hosts": removed_hosts,
        "added_requests": added_requests[:200],
        "removed_requests": removed_requests[:200],
        "status_changes": status_changes[:100],
        "old_request_count": len(old),
        "new_request_count": len(new),
    }


# -------------------------------------------------------------------- screenshot


def diff_screenshot(old_png: bytes | None, new_png: bytes | None) -> tuple[dict, bytes | None]:
    if not old_png or not new_png:
        return {"available": False, "changed": False}, None

    before = Image.open(io.BytesIO(old_png)).convert("RGB")
    after = Image.open(io.BytesIO(new_png)).convert("RGB")
    size_changed = before.size != after.size
    aligned = after.resize(before.size) if size_changed else after

    diff = ImageChops.difference(before, aligned)
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean) / len(stat.mean)
    rms = sum(stat.rms) / len(stat.rms)

    gray = diff.convert("L")
    total = before.size[0] * before.size[1]
    changed_pixels = sum(gray.histogram()[_PIXEL_THRESHOLD:])
    changed_ratio = (changed_pixels / total) if total else 0.0
    similarity = round(1.0 - min(mean / 255.0, 1.0), 4)
    changed = size_changed or changed_ratio > 0.005

    # Red-tint changed regions over the new screenshot to make the diff legible.
    mask = gray.point(lambda p: 200 if p > _PIXEL_THRESHOLD else 0)
    overlay = Image.composite(Image.new("RGB", aligned.size, (255, 0, 0)), aligned, mask)
    buf = io.BytesIO()
    overlay.save(buf, format="PNG")

    summary = {
        "available": True,
        "changed": changed,
        "similarity": similarity,
        "changed_ratio": round(changed_ratio, 4),
        "mean_diff": round(mean, 3),
        "rms": round(rms, 3),
        "size_changed": size_changed,
        "old_size": list(before.size),
        "new_size": list(after.size),
    }
    return summary, buf.getvalue()


# ------------------------------------------------------------------------ result


def diff_result(old_result: dict | None, new_result: dict | None) -> dict:
    old = parse_highlights(old_result)
    new = parse_highlights(new_result)
    tech_added = sorted(set(new["technologies"]) - set(old["technologies"]))
    tech_removed = sorted(set(old["technologies"]) - set(new["technologies"]))
    categories_added = sorted(set(new["categories"]) - set(old["categories"]))
    ips_added = sorted(set(new["ips"]) - set(old["ips"]))
    ips_removed = sorted(set(old["ips"]) - set(new["ips"]))

    verdict_change = (
        {"from": old["malicious"], "to": new["malicious"]}
        if old["malicious"] != new["malicious"]
        else None
    )
    title_change = (
        {"from": old["title"], "to": new["title"]} if old["title"] != new["title"] else None
    )
    final_url_change = (
        {"from": old["final_url"], "to": new["final_url"]}
        if old["final_url"] != new["final_url"]
        else None
    )
    changed = any(
        [
            tech_added,
            tech_removed,
            categories_added,
            ips_added,
            ips_removed,
            verdict_change,
            title_change,
            final_url_change,
        ]
    )
    return {
        "available": old_result is not None and new_result is not None,
        "changed": bool(changed),
        "now_malicious": new["malicious"],
        "verdict_change": verdict_change,
        "categories_added": categories_added,
        "technologies_added": tech_added,
        "technologies_removed": tech_removed,
        "title_change": title_change,
        "final_url_change": final_url_change,
        "ips_added": ips_added,
        "ips_removed": ips_removed,
    }


# --------------------------------------------------------------------- aggregate


def compute_diff(old: ScanArtifacts, new: ScanArtifacts) -> DiffOutcome:
    dom = diff_dom(old.dom, new.dom)
    har = diff_har(old.har, new.har)
    shot_summary, shot_png = diff_screenshot(old.screenshot, new.screenshot)
    result = diff_result(old.result, new.result)

    signals: list[tuple[int, str]] = []
    if result.get("verdict_change") and result.get("now_malicious"):
        signals.append((3, "verdict_became_malicious"))
    elif result.get("verdict_change"):
        signals.append((1, "verdict_changed"))
    if result.get("categories_added"):
        signals.append((3, "new_threat_categories"))
    if har.get("added_hosts"):
        signals.append((2, "new_external_hosts"))
    if har.get("removed_hosts"):
        signals.append((1, "removed_hosts"))
    if har.get("status_changes"):
        signals.append((1, "request_status_changes"))
    if result.get("technologies_added") or result.get("technologies_removed"):
        signals.append((1, "technology_changes"))
    if result.get("final_url_change"):
        signals.append((2, "final_url_changed"))
    if dom.get("changed"):
        signals.append((2 if dom.get("similarity", 1.0) < 0.9 else 1, "dom_changed"))
    if shot_summary.get("changed"):
        signals.append((2 if shot_summary.get("changed_ratio", 0) > 0.1 else 1, "visual_changed"))

    rank = max((rank for rank, _ in signals), default=0)
    severity = _SEVERITY_NAMES[rank]
    summary = {
        "changed": rank > 0,
        "severity": severity,
        "signals": [label for _, label in signals],
        "screenshot": shot_summary,
        "dom": dom,
        "har": har,
        "result": result,
    }
    return DiffOutcome(
        changed=rank > 0,
        severity=severity,
        summary=summary,
        screenshot_diff=shot_png,
    )
