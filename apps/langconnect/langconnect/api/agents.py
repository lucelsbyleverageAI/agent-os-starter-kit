"""
Agent collaboration API endpoints for graph and assistant management.

This module serves as the main router orchestrator, combining:
- Graph lifecycle management (scan, initialize, cleanup)
- Graph permission management (list, grant, revoke access)
- Assistant lifecycle management (list, register, update, delete, sync)
- Assistant permission management (share, revoke access, view permissions)

The endpoints are organized into logical modules for better maintainability:
- graph_actions/ - Graph discovery, initialization, cleanup, and permissions
- assistant_actions/ - Assistant registration, updates, deletion, sharing, and permissions
"""

import logging
from fastapi import APIRouter

from .graph_actions import graph_router
from .assistant_actions import assistant_router
from . import admin_actions
from . import mirror_apis

# Set up logging
log = logging.getLogger(__name__)

# Create main router
router = APIRouter(prefix="/agents")

# Include sub-routers
router.include_router(graph_router)
router.include_router(assistant_router)
router.include_router(admin_actions.router)
router.include_router(mirror_apis.router)

# Export router for server registration
agents_router = router

# Log the refactoring completion
log.info("Agent collaboration API V2 loaded with modular architecture")
log.info("- Graph actions: lifecycle + permissions")
log.info("- Assistant actions: lifecycle + permissions")
log.info("- Activity logging: CRUD operations only (read-only operations no longer logged)")

# ==================== MODULE SUMMARY ====================
#
# 📊 GRAPH MANAGEMENT (graph_actions/)
# ├── lifecycle.py
# │   ├── GET /graphs/scan - Discover and validate graphs ✅ (no activity logging)
# │   ├── POST /graphs/{id}/initialize - Setup new graph ✅ (logs activity)
# │   └── DELETE /graphs/cleanup - Remove orphaned graphs ✅ (logs activity)
# └── permissions.py
#     ├── GET /graphs - List accessible graphs ✅ (no activity logging)
#     ├── GET /graphs/{id}/permissions - Get permissions ✅ (no activity logging)
#     ├── POST /graphs/{id}/permissions - Grant access ✅ (logs activity)
#     └── DELETE /graphs/{id}/permissions/{user} - Revoke access ✅ (logs activity)
#
# 🤖 ASSISTANT MANAGEMENT (assistant_actions/)
# ├── lifecycle.py
# │   ├── GET /assistants - List accessible assistants ✅ (no activity logging)
# │   ├── POST /assistants - Register assistant ✅ (logs activity)
# │   ├── GET /assistants/{id} - Get details ✅ (no activity logging)
# │   ├── PATCH /assistants/{id} - Update assistant ✅ (logs activity)
# │   ├── DELETE /assistants/{id} - Delete assistant ✅ (logs activity)
# │   └── POST /assistants/sync - Sync from LangGraph ✅ (logs activity)
# └── permissions.py
#     ├── POST /assistants/{id}/share - Share assistant ✅ (logs activity)
#     ├── DELETE /assistants/{id}/permissions/{user} - Revoke access ✅ (logs activity)
#     └── GET /assistants/{id}/permissions - Get sharing details ✅ (no activity logging)
#
# ==================== BENEFITS ACHIEVED ====================
#
# ✅ Activity Logging Cleanup:
#    - Removed from 6 read-only operations
#    - Kept for 10 CRUD operations
#    - Cleaner audit trails focusing on actual changes
#
# ✅ Modular Architecture:
#    - 4 focused modules vs 1 monolithic file
#    - Clear separation: lifecycle vs permissions
#    - Easier testing and maintenance
#
# ✅ Reduced Complexity:
#    - ~2,300 lines → ~600 lines per module
#    - Single responsibility per module
#    - Reusable components
#
# ✅ Better Organization:
#    - graph_actions/ and assistant_actions/ namespaces
#    - Logical grouping of related endpoints
#    - Cleaner import structure
