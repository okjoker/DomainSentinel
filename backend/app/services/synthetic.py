"""Deterministic synthetic scan artifacts for the fake Cloudflare client.

Content is derived from two seeds: one from the URL (stable across scans of the
same domain) and one from the scan id (changes every scan). This produces
realistic diffs — a mostly-stable page with a few changing third-party hosts,
content blocks and an occasional "malicious" verdict — so the whole app is
demoable end-to-end without Cloudflare credentials.
"""

from __future__ import annotations

import hashlib
import io
import random
from urllib.parse import urlparse

from PIL import Image, ImageDraw

_STABLE_HOST_POOL = [
    "fonts.googleapis.com",
    "cdnjs.cloudflare.com",
    "www.google-analytics.com",
    "ajax.googleapis.com",
    "static.cloudflareinsights.com",
]
_VOLATILE_HOST_POOL = [
    "ads.doubleclick.net",
    "track.example-ads.com",
    "beacon.metrics.io",
    "pixel.tracker.net",
    "cdn.suspicious-host.ru",
    "analytics.newvendor.io",
    "tag.partner.co",
]
_TECH_POOL = ["nginx", "React", "Cloudflare", "jQuery", "WordPress", "HSTS", "Webpack"]
_DNS_PROVIDER_POOL = [
    "cloudflare.com",
    "awsdns.net",
    "googledomains.com",
    "registrar-servers.com",
    "digitalocean.com",
]
_MAIL_PROVIDER_POOL = [
    "google.com",
    "outlook.com",
    "zoho.com",
    "fastmail.com",
]


def _seed(value: str) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % (2**32)


def derive_content(url: str, scan_uuid: str) -> dict:
    """Derive a content descriptor from the URL (stable) and scan id (volatile)."""
    host = urlparse(url).netloc or urlparse(f"//{url}").netloc or url or "example.com"
    url_rng = random.Random(_seed(url or host))
    scan_rng = random.Random(_seed(scan_uuid))

    stable_hosts = sorted(set(url_rng.sample(_STABLE_HOST_POOL, k=3) + [f"cdn.{host}"]))
    volatile_hosts = sorted(set(scan_rng.sample(_VOLATILE_HOST_POOL, k=scan_rng.randint(1, 3))))
    hosts = sorted(set([host, *stable_hosts, *volatile_hosts]))

    malicious = scan_rng.randint(0, 5) == 0
    technologies = sorted(set(url_rng.sample(_TECH_POOL, k=3) + (["Coinhive"] if malicious else [])))

    return {
        "host": host,
        "url": url,
        "hosts": hosts,
        "stable_hosts": stable_hosts,
        "volatile_hosts": volatile_hosts,
        "title": f"{host} — Home (build {scan_rng.randint(1000, 9999)})",
        "malicious": malicious,
        "categories": ["malware"] if malicious else [],
        "technologies": technologies,
        "item_count": scan_rng.randint(3, 8),
        "url_seed": _seed(url or host),
        "scan_seed": _seed(scan_uuid),
    }


def make_dns_records(content: dict) -> dict:
    """Synthetic NS/MX/TXT/SPF/DMARC records for the fake scanner.

    Stable records derive from the URL seed; the scan seed occasionally mutates
    one dimension (new TXT record, SPF include swap, DMARC policy change, NS
    provider move) so DNS diffs are demoable without being constant noise.
    """
    # XOR the seeds so these streams are independent of the screenshot/HAR ones.
    url_rng = random.Random(content["url_seed"] ^ 0xD25)
    scan_rng = random.Random(content["scan_seed"] ^ 0xD25)
    zone = content["host"].removeprefix("www.")

    dns_provider = url_rng.choice(_DNS_PROVIDER_POOL)
    mail_provider = url_rng.choice(_MAIL_PROVIDER_POOL)
    ns = [f"ns1.{dns_provider}", f"ns2.{dns_provider}"]
    mx = [f"10 mx1.{mail_provider}", f"20 mx2.{mail_provider}"]
    spf = [f"v=spf1 include:_spf.{mail_provider} -all"]
    dmarc = [f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{zone}"]
    txt = [f"google-site-verification={url_rng.getrandbits(64):016x}"]

    roll = scan_rng.random()
    if roll < 0.15:  # a service verification record appeared
        txt.append(f"{scan_rng.choice(['ms', 'stripe', 'atlassian'])}-verify={scan_rng.getrandbits(48):012x}")
    elif roll < 0.25:  # mail was moved to a different provider
        other = scan_rng.choice([p for p in _MAIL_PROVIDER_POOL if p != mail_provider])
        spf = [f"v=spf1 include:_spf.{other} -all"]
    elif roll < 0.33:  # DMARC policy weakened
        dmarc = [f"v=DMARC1; p=none; rua=mailto:dmarc@{zone}"]
    elif roll < 0.40:  # nameservers moved to a different provider
        other = scan_rng.choice([p for p in _DNS_PROVIDER_POOL if p != dns_provider])
        ns = [f"ns1.{other}", f"ns2.{other}"]

    return {
        "available": True,
        "hostname": content["host"],
        "zone": zone,
        "ns": sorted(ns),
        "mx": sorted(mx),
        "txt": sorted(txt + spf),
        "spf": sorted(spf),
        "dmarc": dmarc,
        "errors": {},
    }


def make_screenshot_png(content: dict, width: int = 1024, height: int = 768) -> bytes:
    url_rng = random.Random(content["url_seed"])
    scan_rng = random.Random(content["scan_seed"])
    img = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(img)

    # Stable header + hero (derived from URL) -> unchanged regions across scans.
    header = (url_rng.randint(20, 200), url_rng.randint(20, 200), url_rng.randint(20, 200))
    draw.rectangle([0, 0, width, 80], fill=header)
    draw.text((20, 32), content["title"][:60], fill=(255, 255, 255))
    hero = url_rng.randint(180, 240)
    draw.rectangle([40, 110, width - 40, 280], fill=(hero, hero, hero))

    # Volatile content blocks (derived from scan id) -> localized visual diffs.
    y = 320
    for _ in range(scan_rng.randint(3, 7)):
        color = (scan_rng.randint(0, 255), scan_rng.randint(0, 255), scan_rng.randint(0, 255))
        x0 = scan_rng.randint(40, width // 2)
        w = scan_rng.randint(120, width // 2)
        h = scan_rng.randint(30, 80)
        draw.rectangle([x0, y, min(x0 + w, width - 40), y + h], fill=color)
        y += h + 20
        if y > height - 60:
            break

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_dom_html(content: dict) -> str:
    scripts = "\n".join(
        f'    <script src="https://{h}/app.js"></script>' for h in content["hosts"]
    )
    items = "\n".join(f"        <li>Item {i + 1}</li>" for i in range(content["item_count"]))
    banner = (
        '    <div class="alert">Unusual activity detected</div>\n' if content["malicious"] else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{content['title']}</title>
{scripts}
  </head>
  <body>
{banner}    <header><h1>{content['host']}</h1></header>
    <nav><a href="/">Home</a> <a href="/about">About</a></nav>
    <main>
      <ul>
{items}
      </ul>
    </main>
    <footer>&copy; {content['host']}</footer>
  </body>
</html>
"""


def make_har(content: dict) -> dict:
    rng = random.Random(content["scan_seed"])
    entries = []
    for host in content["hosts"]:
        is_main = host == content["host"]
        entries.append(
            {
                "request": {"method": "GET", "url": f"https://{host}/"},
                "response": {
                    "status": 200,
                    "content": {
                        "mimeType": "text/html" if is_main else "application/javascript",
                        "size": rng.randint(500, 50000),
                    },
                },
                "_resourceType": "document" if is_main else "script",
            }
        )
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "DomainSentinel-fake", "version": "1.0"},
            "entries": entries,
        }
    }


def make_result(content: dict, scan_uuid: str) -> dict:
    """Mimic the parts of a Cloudflare v2 result JSON that DomainSentinel reads."""
    return {
        "task": {"url": content["url"], "uuid": scan_uuid, "success": True},
        "page": {
            "url": content["url"],
            "domain": content["host"],
            "title": content["title"],
        },
        "verdicts": {
            "overall": {
                "malicious": content["malicious"],
                "categories": content["categories"],
            }
        },
        "meta": {
            "processors": {
                "tech": {"data": [{"name": t} for t in content["technologies"]]}
            }
        },
        "lists": {
            "domains": content["hosts"],
            "ips": [f"203.0.113.{content['scan_seed'] % 254 + 1}"],
            "certificates": [{"subjectName": content["host"], "issuer": "FakeCA"}],
        },
    }
