"""DNS record collection: NS, MX, TXT, SPF and DMARC for a monitored domain.

Records are captured alongside each scan so the differ can alert on changes
between scans (nameserver hijacks, MX redirects, SPF/DMARC weakening, new TXT
records). Lookups run against the zone apex — found by walking up from the URL
hostname until NS records answer — because that is where NS/MX/SPF/DMARC live
even when the monitored URL is a subdomain.

Each record type is looked up independently: an empty answer (NXDOMAIN/NoAnswer)
is a real observation stored as ``[]``, while a lookup failure (timeout, SERVFAIL)
stores ``None`` plus an entry in ``errors`` so the differ can skip that type
instead of raising a false alert. ``collect`` never raises.

In fake/demo mode (no Cloudflare credentials) deterministic synthetic records
are generated instead, matching the behaviour of ``FakeCloudflareClient``.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from ..config import get_settings
from . import synthetic

logger = logging.getLogger("domainsentinel.dns")

RECORD_TYPES = ("ns", "mx", "txt", "spf", "dmarc")

_LOOKUP_TIMEOUT = 10.0


def _hostname(url: str) -> str:
    return urlparse(url).netloc or urlparse(f"//{url}").netloc or url


async def collect(url: str, scan_uuid: str | None = None) -> dict:
    """Collect DNS records for a URL's domain. Never raises.

    Returns ``{"available": bool, "hostname": ..., "zone": ..., "ns": [...],
    "mx": [...], "txt": [...], "spf": [...], "dmarc": [...], "errors": {...}}``.
    A record type is ``None`` (with an ``errors`` entry) when its lookup failed.
    """
    hostname = _hostname(url)
    if get_settings().use_fake_cloudflare:
        content = synthetic.derive_content(url, scan_uuid or url)
        return synthetic.make_dns_records(content)
    try:
        return await _collect_real(hostname)
    except Exception as exc:  # noqa: BLE001 — DNS capture must never fail a scan
        logger.warning("dns collection for %s failed: %s", hostname, exc)
        return {"available": False, "hostname": hostname, "error": str(exc)}


async def _collect_real(hostname: str) -> dict:
    # Imported lazily so fake/offline deployments do not require dnspython.
    import dns.asyncresolver
    from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers

    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = _LOOKUP_TIMEOUT

    empty_answer = (NXDOMAIN, NoAnswer, NoNameservers)
    errors: dict[str, str] = {}

    async def query(name: str, rdtype: str) -> list[str] | None:
        """Sorted record strings; [] on an empty answer; None on lookup failure."""
        try:
            answer = await resolver.resolve(name, rdtype)
        except empty_answer:
            return []
        except Exception as exc:  # noqa: BLE001 — timeout/SERVFAIL etc.
            errors[f"{rdtype.lower()}:{name}"] = str(exc) or type(exc).__name__
            return None
        return sorted(rr.to_text().strip('"') for rr in answer)

    # Walk up from the hostname to the enclosing zone (where NS records answer).
    zone, ns = hostname, None
    walk_failed = False
    labels = hostname.rstrip(".").split(".")
    for i in range(max(len(labels) - 1, 1)):
        candidate = ".".join(labels[i:])
        found = await query(candidate, "NS")
        if found is None:
            walk_failed = True
        elif found:
            zone, ns = candidate, sorted(n.rstrip(".").lower() for n in found)
            break
    if ns is None and not walk_failed:
        # Every level answered definitively empty: the domain has no NS records
        # (e.g. expired/unregistered). That is an observation, not a failure.
        ns = []

    mx_raw = await query(zone, "MX")
    mx = sorted(m.rstrip(".").lower() for m in mx_raw) if mx_raw is not None else None
    txt = await query(zone, "TXT")
    dmarc_txt = await query(f"_dmarc.{zone}", "TXT")

    spf = (
        [t for t in txt if t.lower().startswith("v=spf1")] if txt is not None else None
    )
    dmarc = (
        [t for t in dmarc_txt if t.lower().startswith("v=dmarc1")]
        if dmarc_txt is not None
        else None
    )

    return {
        "available": True,
        "hostname": hostname,
        "zone": zone,
        "ns": ns,
        "mx": mx,
        "txt": txt,
        "spf": spf,
        "dmarc": dmarc,
        "errors": errors,
    }
