"""Application configuration, sourced from environment variables / .env.

All persistence is local-first by default (SQLite + local filesystem) so the app
runs with zero external dependencies. Pointing ``DATABASE_URL`` at Postgres and
``BLOB_BACKEND`` at ``gcs`` switches to the GCP backends with no code changes.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Cloudflare URL Scanner v2 ---
    cf_api_token: str = ""
    cf_account_id: str = ""
    cf_api_base: str = "https://api.cloudflare.com/client/v4"
    cf_visibility: str = "Unlisted"
    # When true (or when no credentials are configured) a synthetic scanner is used
    # so the whole app runs offline for local dev, demos and tests.
    cf_fake: bool = False

    # --- Database (SQLAlchemy async URL) ---
    database_url: str = "sqlite+aiosqlite:///./data/domainsentinel.db"

    # --- Blob storage ---
    blob_backend: str = "local"  # "local" | "gcs"
    blob_local_dir: str = "./data/blobs"
    gcs_bucket: str = ""
    gcs_prefix: str = "domainsentinel"

    # --- Scanning / scheduling ---
    default_scan_interval_hours: float = 24.0
    screenshot_resolutions: str = "desktop"  # comma separated: desktop,mobile,tablet
    scan_poll_timeout_seconds: int = 180
    scan_poll_interval_seconds: int = 10
    # In-process scheduler that advances in-flight scans and submits due rescans.
    # Disable in production if you drive /api/cron/tick from Cloud Scheduler instead.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    # Spawn a background poll task on on-demand scans for snappy UX. Disabled in
    # tests so the lifecycle can be driven deterministically via the cron tick.
    autostart_scans: bool = True

    # --- Security ---
    cron_secret: str = ""

    # --- Server ---
    port: int = 8080
    # Directory of the built SPA. Empty -> auto-detect ../frontend/dist (local dev).
    static_dir: str = ""
    cors_origins: str = "*"  # comma separated, or "*"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def screenshot_resolution_list(self) -> list[str]:
        return [r.strip() for r in self.screenshot_resolutions.split(",") if r.strip()] or ["desktop"]

    @property
    def use_fake_cloudflare(self) -> bool:
        return self.cf_fake or not (self.cf_api_token and self.cf_account_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
