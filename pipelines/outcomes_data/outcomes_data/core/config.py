from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple
from urllib.parse import quote, urlparse, urlunparse

import psycopg
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _inject_tenant_into_db_url(db_url: str, tenant: str | None) -> str:
    """Return a DB URL with user@tenant if tenant is set and missing.

    Keeps password, host, port and database unchanged; re-encodes username.
    """
    if not db_url or not tenant:
        return db_url
    parsed = urlparse(db_url)
    if not parsed.username:
        return db_url
    if "@" in parsed.username:
        return db_url
    # Build new netloc with user@tenant and existing password/host/port
    new_username = quote(f"{parsed.username}@{tenant}", safe="")
    password = parsed.password or ""
    auth = new_username if not password else f"{new_username}:{quote(password, safe='')}"
    hostport = parsed.hostname or ""
    if parsed.port:
        hostport = f"{hostport}:{parsed.port}"
    new_netloc = f"{auth}@{hostport}"
    return urlunparse((parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database configuration
    db_url: str | None = Field(default=None, alias="DB_URL")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: str = Field(default="5434", alias="POSTGRES_PORT")
    postgres_db: str = Field(default="postgres", alias="POSTGRES_DB")
    postgres_password: str = Field(default="localpass", alias="POSTGRES_PASSWORD")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    pooler_tenant_id: str | None = Field(default=None, alias="POOLER_TENANT_ID")
    pooler_host: str | None = Field(default=None, alias="POOLER_HOST")
    pooler_port: str | None = Field(default=None, alias="POOLER_PORT")

    # Data source URLs
    rtt_top_url: str = Field(
        default="https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/",
        alias="RTT_TOP_URL",
    )
    cancer_top_url: str = Field(
        default="https://www.england.nhs.uk/statistics/statistical-work-areas/cancer-waiting-times/monthly-data-and-summaries/",
        alias="CANCER_TOP_URL",
    )

    # Oversight Framework URLs
    oversight_metrics_acute: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-acute-trust-data.csv",
        alias="OVERSIGHT_METRICS_ACUTE",
    )
    oversight_metrics_non_acute: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-non-acute-hospital-trust-data.csv",
        alias="OVERSIGHT_METRICS_NON_ACUTE",
    )
    oversight_metrics_ambulance: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-ambulance-trust-data.csv",
        alias="OVERSIGHT_METRICS_AMBULANCE",
    )
    oversight_league_table_acute: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-acute-trust-league-table.csv",
        alias="OVERSIGHT_LEAGUE_TABLE_ACUTE",
    )
    oversight_league_table_non_acute: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-non-acute-hospital-trust-league-table.csv",
        alias="OVERSIGHT_LEAGUE_TABLE_NON_ACUTE",
    )
    oversight_league_table_ambulance: str = Field(
        default="https://www.england.nhs.uk/wp-content/uploads/2025/09/nhs-oversight-framework-ambulance-trust-league-table.csv",
        alias="OVERSIGHT_LEAGUE_TABLE_AMBULANCE",
    )

    # ODS (Organisation Data Service) API
    ods_base_url: str = Field(
        default="https://sandbox.api.service.nhs.uk/organisation-data-terminology-api",
        alias="ODS_BASE_URL",
    )
    ods_api_key: str | None = Field(default=None, alias="ODS_API_KEY")

    # Cache and performance
    cache_root: Path = Field(default=Path(".cache"), alias="CACHE_ROOT")
    http_timeout_s: int = Field(default=60, alias="HTTP_TIMEOUT_S")
    http_retries: int = Field(default=3, alias="HTTP_RETRIES")
    download_pool: int = Field(default=4, alias="DOWNLOAD_POOL")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @computed_field
    @property
    def effective_db_url(self) -> str:
        """Compute the effective database URL with tenant injection if needed."""
        # If DB_URL is provided, use it with tenant injection
        if self.db_url:
            return _inject_tenant_into_db_url(self.db_url, self.pooler_tenant_id)

        # Build DSN from discrete env vars (similar to V1 logic)
        host = self.postgres_host
        port = self.postgres_port
        dbname = self.postgres_db
        password = self.postgres_password
        base_user = self.postgres_user
        tenant = self.pooler_tenant_id

        # If using Supavisor, tenant is required: user@tenant
        if tenant and "@" not in base_user:
            base_user = f"{base_user}@{tenant}"

        # Prefer pooler host/port when tenant is set and overrides are provided
        if tenant:
            host = self.pooler_host or host
            port = self.pooler_port or port

        user = quote(base_user, safe="")  # encode '@' if present
        return f"postgres://{user}:{password}@{host}:{port}/{dbname}"


def load_settings() -> Settings:
    """Load settings from environment variables and .env file."""
    return Settings()


def test_db_connection(settings: Settings) -> Tuple[bool, str]:
    """Try connecting to Postgres and return (ok, message).

    - Uses the resolved `settings.effective_db_url`.
    - Executes a trivial query to validate connectivity.
    """
    db_url = settings.effective_db_url
    if not db_url:
        return False, "DB URL is not configured (settings.effective_db_url is None)."

    try:
        # Short timeout to fail fast if unreachable
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("select version()")
                row = cur.fetchone()
                version = row[0] if row else "unknown"
        return True, f"Connected successfully. Server: {version}"
    except Exception as exc:  # noqa: BLE001 - surface exact failure to caller
        return False, f"Connection failed: {exc}"


if __name__ == "__main__":
    # Allow quick manual testing: `poetry run python -m outcomes_data.core.config`
    s = load_settings()
    # Lightweight debug of the target (password redacted)
    try:
        _u = urlparse(s.effective_db_url or "")
        print(f"Target -> user={_u.username} host={_u.hostname} port={_u.port} db={_u.path.lstrip('/')}")
    except Exception:
        pass
    ok, msg = test_db_connection(s)
    print(("OK" if ok else "FAIL"), msg)
