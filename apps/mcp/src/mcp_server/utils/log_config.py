"""Logging configuration for the MCP server."""

import logging
import sys
from typing import Any, Dict

import structlog
from structlog.typing import FilteringBoundLogger

from ..config import settings


def configure_logging() -> FilteringBoundLogger:
    """Configure structured logging for the application."""
    
    # Configure standard library logging
    # We attach a ProcessorFormatter so structlog records flow through stdlib and are captured by Sentry's LoggingIntegration
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(getattr(logging, settings.mcp_log_level.upper()))

    # Configure structlog to use stdlib logger factory and wrap for ProcessorFormatter
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.mcp_log_level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer(),
        ]
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    return structlog.get_logger()


def get_logger(name: str = __name__) -> FilteringBoundLogger:
    """Get a logger instance with the given name."""
    return structlog.get_logger(name)


def log_request(logger: FilteringBoundLogger, method: str, path: str, **kwargs: Any) -> None:
    """Log an incoming request."""
    logger.info(
        "Request received",
        method=method,
        path=path,
        **kwargs
    )


def log_response(
    logger: FilteringBoundLogger, 
    method: str, 
    path: str, 
    status_code: int, 
    duration_ms: float,
    **kwargs: Any
) -> None:
    """Log a response."""
    logger.info(
        "Request completed",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_error(
    logger: FilteringBoundLogger, 
    error: Exception, 
    context: Dict[str, Any] = None
) -> None:
    """Log an error with context."""
    logger.error(
        "Error occurred",
        error=str(error),
        error_type=type(error).__name__,
        **(context or {})
    ) 