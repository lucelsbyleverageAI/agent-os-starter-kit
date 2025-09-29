import logging
import os


def init_sentry() -> None:
    """Initialise Sentry and logging for MCP.

    Initialises Sentry if a DSN is provided, and configures structlog.
    Uses Starlette and logging integrations. INFO logs become breadcrumbs,
    ERROR and above become events.
    
    Mirrors LangGraph pattern for consistency across services.
    """
    # First, configure logging so Sentry can hook into it
    from .utils.logging import configure_logging
    configure_logging()

    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.starlette import StarletteIntegration  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    except Exception:
        return

    dsn = os.environ.get("SENTRY_DSN_MCP") or os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(  # type: ignore
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),  # type: ignore
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),  # type: ignore
        ],
        # Quiet production consoles - mirror LangGraph pattern
        enable_logs=True,
        before_send=_sanitize_event,
        before_breadcrumb=_sanitize_breadcrumb,
    )


def _sanitize_event(event, hint):
    """Sanitize Sentry events to remove sensitive data."""
    # Remove sensitive headers
    if 'request' in event and 'headers' in event['request']:
        headers = event['request']['headers']
        sensitive_headers = ['authorization', 'api-key', 'token', 'cookie', 'x-supabase-access-token']
        for header in sensitive_headers:
            if header in headers:
                headers[header] = '[Redacted]'
    
    return event


def _sanitize_breadcrumb(crumb, hint):
    """Sanitize breadcrumbs to remove sensitive data."""
    # Remove sensitive data from breadcrumb data
    if 'data' in crumb:
        data = crumb['data']
        sensitive_keys = ['token', 'authorization', 'api_key', 'password', 'jwt_token']
        for key in sensitive_keys:
            if key in data:
                data[key] = '[Redacted]'
    
    return crumb


def get_logger(name: str | None = None):
    """Return the structlog logger bound through our config.

    This ensures we can pass structured key=value pairs like
    logger.info("msg", key=value) without raising TypeError on stdlib loggers.
    """
    try:
        from .utils.log_config import get_logger as _get_struct_logger
        return _get_struct_logger(name or __name__)
    except Exception:
        # Fallback to stdlib logger if structlog is unavailable
        return logging.getLogger(name)


