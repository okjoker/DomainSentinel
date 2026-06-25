# Deploying DomainSentinel to GCP Cloud Run

This walks through a production deployment using **Cloud Run** + **Cloud SQL
(Postgres)** + **Cloud Storage** + **Cloud Scheduler**. The image is built so
that switching from the local-first defaults to the GCP backends is purely a
matter of environment variables (asyncpg and google-cloud-storage are already
baked into the image).

## 0. Prerequisites

```bash
export PROJECT_ID=your-project
export REGION=us-central1
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  storage.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 1. Cloud Storage bucket (artifacts)

```bash
export BUCKET=${PROJECT_ID}-domainsentinel
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
```

## 2. Cloud SQL (Postgres) — optional but recommended

```bash
gcloud sql instances create domainsentinel-db --database-version=POSTGRES_16 \
  --tier=db-f1-micro --region=$REGION
gcloud sql databases create domainsentinel --instance=domainsentinel-db
gcloud sql users create app --instance=domainsentinel-db --password=CHANGE_ME
# Connection name looks like: PROJECT:REGION:domainsentinel-db
```

With the Cloud SQL connector attached to the service, use a Unix-socket URL:

```
DATABASE_URL=postgresql+asyncpg://app:CHANGE_ME@/domainsentinel?host=/cloudsql/PROJECT:REGION:domainsentinel-db
```

> Skipping Postgres? Leave `DATABASE_URL` on the SQLite default. Note the SQLite
> file lives on the container's ephemeral disk and is **lost on each cold start**,
> so Postgres is strongly recommended for anything beyond a demo.

## 3. Store the Cloudflare token as a secret

```bash
echo -n "YOUR_CF_TOKEN" | gcloud secrets create cf-api-token --data-file=-
echo -n "$(openssl rand -hex 16)" | gcloud secrets create ds-cron-secret --data-file=-
```

## 4. Build & deploy

```bash
gcloud run deploy domainsentinel \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --min-instances=1 \
  --add-cloudsql-instances PROJECT:REGION:domainsentinel-db \
  --set-env-vars "CF_ACCOUNT_ID=YOUR_ACCOUNT_ID" \
  --set-env-vars "BLOB_BACKEND=gcs,GCS_BUCKET=$BUCKET" \
  --set-env-vars "DATABASE_URL=postgresql+asyncpg://app:CHANGE_ME@/domainsentinel?host=/cloudsql/PROJECT:REGION:domainsentinel-db" \
  --set-env-vars "SCHEDULER_ENABLED=false" \
  --set-secrets "CF_API_TOKEN=cf-api-token:latest,CRON_SECRET=ds-cron-secret:latest"
```

Notes:
- Grant the service's runtime service account `roles/storage.objectAdmin` on the
  bucket and `roles/cloudsql.client`.
- `--min-instances=1` keeps an instance warm so in-flight scan polling completes
  promptly. With the external scheduler below you can also scale to zero.
- `SCHEDULER_ENABLED=false` disables the in-process scheduler; Cloud Scheduler
  drives the tick instead (next step), which is the right model when Cloud Run
  may run multiple instances.

## 5. Cloud Scheduler → /api/cron/tick

```bash
export URL=$(gcloud run services describe domainsentinel --region $REGION --format='value(status.url)')
export CRON_SECRET=$(gcloud secrets versions access latest --secret=ds-cron-secret)

gcloud scheduler jobs create http domainsentinel-tick \
  --location $REGION \
  --schedule "*/5 * * * *" \
  --uri "$URL/api/cron/tick" \
  --http-method POST \
  --headers "X-Cron-Secret=$CRON_SECRET"
```

The tick submits due rescans and advances any in-flight scans. Tune the cron
schedule and per-domain `interval_hours` to taste (mind Cloudflare's URL Scanner
rate limits).

## 6. Verify

```bash
curl -s $URL/healthz
curl -s -X POST $URL/api/domains -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com"}'
```

Then open `$URL` in a browser for the dashboard.
