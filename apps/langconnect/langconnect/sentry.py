import logging
import os


def init_sentry() -> None:
    """Initialise Sentry for LangConnect if DSN is provided.

    Uses FastAPI and logging integrations. INFO logs become breadcrumbs,
    ERROR and above become events. PII is disabled by default.
    """
    try:  # Optional dependency
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    except Exception:
        return

    dsn = os.environ.get("SENTRY_DSN_LANGCONNECT") or os.environ.get("SENTRY_DSN")

    # Skip Sentry if DSN is not set or is a placeholder value
    if not dsn or dsn in ["your-sentry-dsn", ""]:
        return

    # Validate DSN format (should start with https:// or http://)
    if not dsn.startswith(("https://", "http://")):
        logging.warning(f"Invalid Sentry DSN format: {dsn[:20]}... (showing first 20 chars)")
        return

    sentry_sdk.init(  # type: ignore
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
        integrations=[
            FastApiIntegration(),  # type: ignore
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),  # type: ignore
        ],
    )


