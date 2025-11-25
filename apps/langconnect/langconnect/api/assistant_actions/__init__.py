"""
Assistant actions module - combining lifecycle, permission, and version management.
"""

from fastapi import APIRouter
from . import lifecycle, permissions, versions

# Create main assistant router
assistant_router = APIRouter()

# Include sub-routers
assistant_router.include_router(lifecycle.router, tags=["assistant-lifecycle"])
assistant_router.include_router(permissions.router, tags=["assistant-permissions"])
assistant_router.include_router(versions.router, tags=["assistant-versions"])

# Export for use in main agents.py
__all__ = ["assistant_router"] 