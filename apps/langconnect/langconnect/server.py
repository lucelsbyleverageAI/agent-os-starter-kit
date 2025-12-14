import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from langconnect.api import collections_router, documents_router, users_router, agents_router, jobs_router, feedback_router
from langconnect.api.usage import router as usage_router
from langconnect.api.chunks import router as chunks_router
from langconnect.api.public_permissions import router as public_permissions_router
from langconnect.api.notifications import router as notifications_router
from langconnect.api.memory import memory_router
from langconnect.api.agent_filesystem import router as agent_filesystem_router
from langconnect.api.default_assistant import router as default_assistant_router
from langconnect.api.storage import router as storage_router
from langconnect.api.skills import router as skills_router
from langconnect.config import ALLOWED_ORIGINS
from langconnect.database.collections import CollectionsManager
from langconnect.services.sync_scheduler import start_sync_scheduler, stop_sync_scheduler
from langconnect.sentry import init_sentry

# Optional Sentry initialisation (only if SDK installed and DSN provided)
try:  # noqa: SIM105
    import sentry_sdk  # type: ignore
    from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
    from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None  # type: ignore

init_sentry()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# Initialize FastAPI app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI application."""
    logger.info("App is starting up. Creating background worker...")
    await CollectionsManager.setup()
    
    # Start LangGraph sync scheduler
    logger.info("Starting LangGraph sync scheduler...")
    await start_sync_scheduler()
    
    yield
    
    logger.info("App is shutting down. Stopping background worker...")
    # Stop LangGraph sync scheduler
    await stop_sync_scheduler()


APP = FastAPI(
    title="LangConnect API",
    description="A REST API for our Langgraph Agent System including APIs for context engineering and agent management & collaboration.",
    version="0.1.0",
    lifespan=lifespan,
)


# Add validation error handler for debugging
@APP.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed validation errors for debugging."""
    logger.error(f"[VALIDATION_ERROR] Request URL: {request.url}")
    logger.error(f"[VALIDATION_ERROR] Request method: {request.method}")
    logger.error(f"[VALIDATION_ERROR] Request headers: {dict(request.headers)}")

    # Try to read the request body for logging
    try:
        body = await request.body()
        logger.error(f"[VALIDATION_ERROR] Request body: {body.decode('utf-8')}")
    except Exception as e:
        logger.error(f"[VALIDATION_ERROR] Could not read request body: {e}")

    logger.error(f"[VALIDATION_ERROR] Validation errors: {exc.errors()}")

    # Convert validation errors to JSON-safe format
    # exc.errors() can contain non-serializable objects like ValueError in 'ctx' field
    json_safe_errors = []
    for error in exc.errors():
        safe_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input")
        }

        # Handle ctx field which may contain exception objects
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict):
                safe_ctx = {}
                for key, value in ctx.items():
                    # Convert non-serializable objects to strings
                    if isinstance(value, Exception):
                        safe_ctx[key] = str(value)
                    else:
                        safe_ctx[key] = value
                safe_error["ctx"] = safe_ctx

        json_safe_errors.append(safe_error)

    # Return the standard FastAPI validation error response
    return JSONResponse(
        status_code=422,
        content={"detail": json_safe_errors},
    )


# Add CORS middleware
APP.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
APP.include_router(collections_router)
APP.include_router(documents_router)
APP.include_router(chunks_router)
APP.include_router(users_router)
APP.include_router(agents_router)
APP.include_router(jobs_router)
APP.include_router(public_permissions_router)
APP.include_router(notifications_router)
APP.include_router(memory_router)
APP.include_router(agent_filesystem_router)
APP.include_router(default_assistant_router)
APP.include_router(storage_router)
APP.include_router(feedback_router)
APP.include_router(skills_router)
APP.include_router(usage_router)


@APP.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
