import logging
import os


def init_sentry() -> None:
    """Optional Sentry initialisation for LangGraph host environments.

    This library does not auto-init Sentry. Call this from the host
    process if you want Sentry. Uses LoggingIntegration so stdlib logs
    at INFO become breadcrumbs and ERROR become events.
    """
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    except Exception:
        return

    dsn = os.environ.get("SENTRY_DSN_LANGGRAPH") or os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(  # type: ignore
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),  # type: ignore
        ],
        enable_logs=True,
    )

    # Send a simple info event to confirm initialisation
    try:
        sentry_sdk.capture_message("LangGraph Sentry initialised", level="info")  # type: ignore
    except Exception:
        pass


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a stdlib logger; host can route it to Sentry via LoggingIntegration."""
    return logging.getLogger(name)


"""
Single Sentry integration surface for LangGraph.
Call init_sentry() once from the host process. Use get_logger(__name__) elsewhere.
"""


