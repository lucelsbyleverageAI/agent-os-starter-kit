"""
Graph actions module - combining lifecycle and permission management.
"""

from fastapi import APIRouter
from . import lifecycle, permissions
from . import presentation

# Create main graph router
graph_router = APIRouter()

# Include sub-routers
graph_router.include_router(lifecycle.router, tags=["graph-lifecycle"])
graph_router.include_router(permissions.router, tags=["graph-permissions"])
graph_router.include_router(presentation.router, tags=["graph-presentation"])

# Export for use in main agents.py
__all__ = ["graph_router"] 