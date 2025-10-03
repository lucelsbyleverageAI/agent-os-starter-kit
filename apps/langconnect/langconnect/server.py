import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langconnect.api import collections_router, documents_router, users_router, agents_router, jobs_router
from langconnect.api.chunks import router as chunks_router
from langconnect.api.public_permissions import router as public_permissions_router
from langconnect.api.notifications import router as notifications_router
from langconnect.api.memory import memory_router
from langconnect.api.agent_filesystem import router as agent_filesystem_router
from langconnect.config import ALLOWED_ORIGINS, IMAGE_STORAGE_ENABLED
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

# Conditionally include GCP images router if enabled
if IMAGE_STORAGE_ENABLED:
    from langconnect.api.gcp_images import router as gcp_images_router
    APP.include_router(gcp_images_router)
    logger.info("GCP Image Storage enabled - mounted /gcp endpoints")
else:
    logger.info("GCP Image Storage disabled - /gcp endpoints not available")


@APP.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
