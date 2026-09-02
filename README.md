# 🛡️ DomainSentinel

Domain **change monitoring** powered by the [Cloudflare URL Scanner](https://developers.cloudflare.com/radar/investigate/url-scanner/).
Ingest domains via an API, scan them on a schedule (screenshot + DOM + HAR +
verdict + DNS), and get the **differences between scans highlighted** — visual
changes, new third-party hosts, DOM edits, threat-verdict flips, and DNS record
changes (NS/MX/TXT/SPF/DMARC).

Built to run as a single container on **GCP Cloud Run**. Runs locally with **zero
configuration** in a demo mode that uses a synthetic scanner, so you can try the
whole thing — including diffs — without any Cloudflare credentials.

---

## What it does

- **Ingest** domains to monitor via `POST /api/domains`.
- **Scan** each URL with the Cloudflare URL Scanner v2 API, capturing the
  **screenshot**, rendered **DOM**, and **HAR** (full network log), plus the
  scan **verdict** and detected technologies.
- **Snapshot DNS** with every scan: **NS**, **MX**, and **TXT** records plus the
  parsed **SPF** and **DMARC** policies for the domain's zone.
- **Re-scan** on demand and on a schedule (per-domain interval).
- **Diff** every new scan against the previous one and surface what changed,
  scored by severity (`none → low → medium → high`).
- **Visualize** it all in a polished React dashboard with a side-by-side diff view.

## How it works

```
React/TS SPA  ──/api──>  FastAPI  ──>  Scanner lifecycle  ──>  Cloudflare URL Scanner v2
   (dashboard,                │              │
    diff view)                │              ├─ Differ (screenshot / DOM / HAR / verdict / DNS)
                              │              │
                       Storage layer         └─ Scheduler (in-process) + POST /api/cron/tick
                       ├─ MetadataStore: SQLAlchemy (SQLite → Postgres)
                       └─ BlobStore:     local filesystem → Google Cloud Storage
```

Cloudflare scanning is **asynchronous**, so each scan moves through a state
machine that is safe on stateless Cloud Run instances:

```
QUEUED ─submit─> SUBMITTED ─result ready─> FETCHING ─artifacts stored─> COMPLETED
                    │ 404 = still scanning (poll)                         │
                    └────────────── timeout ──────────────> FAILED        └─> auto-diff vs previous
```

A single **tick** (`POST /api/cron/tick`, also run by an in-process scheduler)
submits due rescans and advances in-flight scans. On-demand scans additionally
kick a background poll for snappy feedback while the instance is warm.

## Tech stack

| Layer      | Choice                                                              |
|------------|--------------------------------------------------------------------|
| Backend    | Python 3.11 · FastAPI · SQLAlchemy 2 (async) · httpx · APScheduler  |
| Diffing    | Pillow (visual) · BeautifulSoup + difflib (DOM) · custom HAR/verdict|
| Frontend   | React 18 · TypeScript · Vite · Tailwind · TanStack Query · Router   |
| Storage    | SQLite + filesystem (default) → Cloud SQL Postgres + GCS (config swap) |
| Packaging  | Multi-stage Docker image · Cloud Run · Cloud Scheduler              |

---

## Quick start (demo mode, no credentials)

### With Docker

```bash
docker compose up --build
# open http://localhost:8080
```

### With Make (local toolchain)

```bash
make setup            # venv + npm install
make build-frontend   # build the SPA (served by the API)
make dev-backend      # http://localhost:8080  (demo mode)
```

Add a domain (e.g. `example.com`) in the UI and click **Scan now** twice — the
synthetic scanner produces realistic, partly-changing artifacts so the diff view
lights up immediately.

## Local development (hot reload)

Run the API and the Vite dev server in two terminals:

```bash
make dev-backend     # FastAPI on :8080 (CF_FAKE=true)
make dev-frontend    # Vite on :5173, proxies /api -> :8080
# develop against http://localhost:5173
```

## Scanning real domains

1. Create a Cloudflare API token with the **Account → URL Scanner: Edit**
   permission, and note your **Account ID**.
2. `cp .env.example .env` and set:
   ```
   CF_API_TOKEN=...
   CF_ACCOUNT_ID=...
   CF_FAKE=false
   ```
3. Restart. (If `CF_API_TOKEN`/`CF_ACCOUNT_ID` are unset, the app automatically
   falls back to the synthetic scanner.)

---

## API reference

| Method & path | Description |
|---|---|
| `POST /api/domains` | Ingest a domain `{url, label?, interval_hours?, scan_now?}` |
| `GET /api/domains` | List monitored domains (with last status + severity) |
| `GET /api/domains/{id}` | Domain detail + scan history + latest diff |
| `PATCH /api/domains/{id}` | Update label / interval / active |
| `DELETE /api/domains/{id}` | Stop monitoring and delete |
| `POST /api/domains/{id}/scan` | Trigger an on-demand scan (202) |
| `GET /api/scans/{id}` | Scan status + parsed highlights |
| `GET /api/scans/{id}/screenshot` · `/dom` · `/har` | Download an artifact |
| `GET /api/domains/{id}/diff/latest` | Most recent diff for a domain |
| `GET /api/domains/{id}/diffs` | All diffs for a domain |
| `POST /api/domains/{id}/diff?from_scan=&to_scan=` | Diff an explicit scan pair (idempotent) |
| `GET /api/diffs/{id}` · `/screenshot` | Diff detail / overlay image |
| `POST /api/cron/tick` | Advance the scan lifecycle (Cloud Scheduler) |
| `GET /healthz` | Health check |

Interactive docs at `/docs` (Swagger UI).

## How diffing works

Each completed scan is compared with the previous completed scan across five
dimensions; the overall **severity** is the strongest signal found:

- **Screenshot** — pixel difference, similarity %, and a red-tinted overlay of
  the changed regions (Pillow).
- **DOM** — normalized HTML line diff (added/removed/unified) + similarity.
- **HAR (network)** — new/removed **hosts**, new/removed requests, and status
  changes. New external hosts are the key security signal (injected scripts,
  trackers, exfil endpoints).
- **Verdict & tech** — malicious-verdict flips, new threat categories,
  added/removed technologies, final-URL/title/IP changes.
- **DNS** — added/removed **NS**, **MX**, **TXT**, **SPF**, and **DMARC**
  records between the two snapshots. Lookups run against the zone apex (found by
  walking up from the URL hostname), and a record type whose lookup failed on
  either side is skipped rather than raising a false alert.

A malicious verdict, a new threat category, or an **NS/MX change** (hijack /
mail-interception indicators) is **high**; new external hosts, a large
visual/DOM change, or an **SPF/DMARC change** is **medium**; minor changes
(including other TXT record churn) are **low**.

## Storage backends (local-first → GCP)

Nothing to change in code — just environment variables:

| | Local (default) | GCP |
|---|---|---|
| Metadata | `DATABASE_URL=sqlite+aiosqlite:///./data/...` | `DATABASE_URL=postgresql+asyncpg://...` |
| Blobs | `BLOB_BACKEND=local` | `BLOB_BACKEND=gcs`, `GCS_BUCKET=...` |

The Docker image ships with `asyncpg` and `google-cloud-storage` preinstalled, so
the same image runs both modes. See [`backend/requirements-gcp.txt`](backend/requirements-gcp.txt)
for local installs.

## Deploy to Cloud Run

See **[deploy/cloudrun.md](deploy/cloudrun.md)** for a full walkthrough (Cloud
Run + Cloud SQL + GCS + Cloud Scheduler, secrets, IAM).

## Testing

```bash
make test
# or: cd backend && .venv/bin/python -m pytest -q
```

The suite covers the diff engine (fixtures), the Cloudflare client (mocked with
`respx`, including the 404→ready polling and 429 paths), and the full API
end-to-end via the synthetic scanner.

## Project layout

```
backend/   FastAPI app (app/), tests/, requirements*.txt
  app/api/        routers: domains, scans, diffs, cron
  app/services/   cloudflare client, synthetic scanner, scanner lifecycle, differ, dns records
  app/storage/    BlobStore (local + GCS)
  app/{config,db,models,schemas,scheduler,main}.py
frontend/  React + TS + Vite + Tailwind SPA (built into dist/, served by the API)
Dockerfile · docker-compose.yml · Makefile · .env.example · deploy/
```

## Configuration

All options live in [`.env.example`](.env.example) with sane defaults
(Cloudflare token, database URL, blob backend, scan interval, scheduler, cron
secret, port).

## Not in this iteration

User auth / multi-tenancy, change alerting (email/Slack/webhook), Alembic
migrations (uses `create_all`), and IaC (documented `gcloud` commands instead).
