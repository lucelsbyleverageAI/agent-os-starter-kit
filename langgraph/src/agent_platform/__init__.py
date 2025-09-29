from .sentry import init_sentry

# Initialise Sentry once when the agent_platform package is imported by the host
try:
    init_sentry()
except Exception:
    # Never break app startup due to Sentry init
    pass

__all__ = [
    "init_sentry",
]

