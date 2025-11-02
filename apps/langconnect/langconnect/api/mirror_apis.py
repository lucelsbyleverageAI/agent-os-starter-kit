"""
Mirror-backed read APIs for graphs, assistants, schemas, and threads.

These endpoints serve data from the mirror tables for fast, consistent reads
with versioned cache support. All mutation operations should go through
the existing lifecycle endpoints which will trigger sync operations.
"""

import logging
from typing import Annotated, Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header, Response, Body
from uuid import UUID
import httpx

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.database.connection import get_db_connection, get_db_pool
import asyncpg
from langconnect.database.permissions import GraphPermissionsManager, AssistantPermissionsManager
from langconnect.services.permission_service import PermissionService
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
from langconnect.services.langgraph_sync import LangGraphSyncService, get_sync_service

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/mirror", tags=["Mirror APIs"])


@router.get("/cache-state")
async def get_cache_state(
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Get current cache state for version-aware frontend caching.
    
    Returns version numbers for each mirror type and last sync time.
    Frontend can use these versions to determine when to invalidate local caches.
    """
    return await sync_service.get_cache_state()


@router.get("/graphs")
async def list_graphs_from_mirror(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    if_none_match: Optional[str] = Header(None, alias="if-none-match")
) -> Dict[str, Any]:
    """
    List graphs from mirror with user permission levels.

    ARCHITECTURE: Independent Endpoint
    ================================================
    This endpoint is called by MULTIPLE consumers:

    1. AGGREGATION PROXY: /api/langconnect/user/accessible-graphs (Next.js)
       - Calls this endpoint + /mirror/assistants to provide combined discovery
       - See: apps/web/src/app/api/langconnect/user/accessible-graphs/route.ts:118

    2. ADMIN UI: retired-graphs-table component (Direct Call)
       - Admin component needs graph lists WITHOUT assistant data overhead
       - See: apps/web/src/components/admin/retired-graphs-table.tsx:113
       - This dependency prevents consolidation

    WHY SEPARATE FROM ASSISTANTS:
    - Independent caching with optimized TTL (5 minutes vs 3 minutes)
    - ETag-based HTTP cache for bandwidth efficiency
    - Admin queries can fetch graphs without pulling assistant data
    - Service accounts can query independently for automation

    CACHING STRATEGY:
    - ETag generation based on graphs_version from cache_state table
    - Returns 304 Not Modified when client ETag matches
    - Cache-Control: private, max-age=300 (5 minutes)
    - Versioning incremented on graph mutations

    PERMISSIONS:
    - Filters by graph_permissions table (user access control)
    - Respects retired graphs (hidden from non-admins)
    - Service accounts see all graphs

    Serves from graphs_mirror joined with user permissions for fast reads.
    """
    try:
        log.info(f"Listing graphs from mirror for {actor.actor_type}:{actor.identity}")
        
        async with get_db_connection() as conn:
            # ========================================================================
            # ETAG CACHING: Independent cache for graphs (5min TTL)
            # ========================================================================
            # This endpoint has its own cache version separate from assistants
            # because graph templates change less frequently than user-created
            # assistants. Admin UI depends on this independent caching.
            # ========================================================================

            # Get cache state for ETag
            cache_state = await conn.fetchrow(
                "SELECT graphs_version FROM langconnect.cache_state WHERE id = 1"
            )
            graphs_version = cache_state["graphs_version"] if cache_state else 1

            # Generate ETag from version
            etag = f'"graphs-v{graphs_version}"'

            # Check if client has current version
            if if_none_match == etag:
                response.status_code = 304
                return {}

            # Set ETag header
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=300"  # 5 minutes soft cache

            # ========================================================================
            # ADMIN UI DEPENDENCY: Retired graphs filter
            # ========================================================================
            # The retired-graphs-table admin component (apps/web/src/components/
            # admin/retired-graphs-table.tsx:113) calls this endpoint directly to
            # manage which graphs are visible to users. This prevents consolidating
            # this endpoint with /mirror/assistants.
            # ========================================================================

            # Exclude retired graphs for non-admin users
            include_retired = False
            if actor.actor_type == "user":
                user_role = await GraphPermissionsManager.get_user_role(actor.identity)
                include_retired = user_role == "dev_admin"

            if actor.actor_type == "service":
                # Service accounts see all graphs
                graphs_query = """
                    SELECT
                        gm.graph_id,
                        gm.assistants_count,
                        gm.has_default_assistant,
                        gm.schema_accessible,
                        gm.name,
                        gm.description,
                        gm.langgraph_first_seen_at,
                        gm.langgraph_last_seen_at,
                        NULL as user_permission_level,
                        NULL as permission_granted_at,
                        (SELECT assistant_id FROM langconnect.assistants_mirror WHERE graph_id = gm.graph_id AND metadata->>'created_by' = 'system' LIMIT 1) as system_assistant_id
                    FROM langconnect.graphs_mirror gm
                    LEFT JOIN langconnect.admin_retired_graphs rg ON rg.graph_id = gm.graph_id AND rg.status = 'marked'
                    WHERE $1::boolean OR rg.graph_id IS NULL
                    ORDER BY gm.graph_id
                """
                graphs = await conn.fetch(graphs_query, include_retired)
            else:
                # Regular users see only graphs they have permission for
                user_graphs = await GraphPermissionsManager.get_user_accessible_graphs(actor.identity)
                accessible_graph_ids = [g["graph_id"] for g in user_graphs]
                
                if not accessible_graph_ids:
                    return {
                        "graphs": [],
                        "total_count": 0,
                        "graphs_version": graphs_version
                    }
                
                # Join with user permissions
                graphs_query = """
                    SELECT
                        gm.graph_id,
                        gm.assistants_count,
                        gm.has_default_assistant,
                        gm.schema_accessible,
                        gm.name,
                        gm.description,
                        gm.langgraph_first_seen_at,
                        gm.langgraph_last_seen_at,
                        gp.permission_level as user_permission_level,
                        gp.created_at as permission_granted_at,
                        (SELECT assistant_id FROM langconnect.assistants_mirror WHERE graph_id = gm.graph_id AND metadata->>'created_by' = 'system' LIMIT 1) as system_assistant_id
                    FROM langconnect.graphs_mirror gm
                    LEFT JOIN langconnect.admin_retired_graphs rg ON rg.graph_id = gm.graph_id AND rg.status = 'marked'
                    LEFT JOIN langconnect.graph_permissions gp ON gm.graph_id = gp.graph_id AND gp.user_id = $1
                    WHERE gm.graph_id = ANY($2) AND ($3::boolean OR rg.graph_id IS NULL)
                    ORDER BY gm.graph_id
                """
                graphs = await conn.fetch(graphs_query, actor.identity, accessible_graph_ids, include_retired)
            
            # Format response
            graphs_list = []
            for graph in graphs:
                # Calculate allowed actions for this graph
                if actor.actor_type == "service":
                    # Service accounts get full access
                    allowed_actions = ["view", "create_assistant", "manage_access"]
                else:
                    # Regular users: calculate based on permissions
                    allowed_actions = await PermissionService.get_allowed_actions(
                        user_id=actor.identity,
                        resource_type="graph",
                        resource_id=graph["graph_id"]
                    )

                graphs_list.append({
                    "graph_id": graph["graph_id"],
                    "assistants_count": graph["assistants_count"],
                    "has_default_assistant": graph["has_default_assistant"],
                    "schema_accessible": graph["schema_accessible"],
                    "name": graph["name"],
                    "description": graph["description"],
                    "user_permission_level": graph["user_permission_level"],
                    "system_assistant_id": str(graph["system_assistant_id"]) if graph["system_assistant_id"] else None,
                    "available": True,
                    "created_at": graph["permission_granted_at"].isoformat() if graph["permission_granted_at"] else None,
                    "allowed_actions": allowed_actions
                })
            
            log.info(f"Listed {len(graphs_list)} graphs from mirror for {actor.actor_type}:{actor.identity}")

            # Include user role in response for frontend permission logic
            user_role = None
            if actor.actor_type == "user":
                user_role = await GraphPermissionsManager.get_user_role(actor.identity)

            return {
                "graphs": graphs_list,
                "total_count": len(graphs_list),
                "graphs_version": graphs_version,
                "user_role": user_role or "user"
            }
            
    except Exception as e:
        log.error(f"Failed to list graphs from mirror: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list graphs from mirror: {str(e)}"
        )


@router.get("/assistants")
async def list_assistants_from_mirror(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)],
    if_none_match: Optional[str] = Header(None, alias="if-none-match")
) -> Dict[str, Any]:
    """
    List assistants from mirror with permission metadata.

    ARCHITECTURE: Independent Endpoint
    ================================================
    This endpoint is called by AGGREGATION PROXY ONLY:

    1. AGGREGATION PROXY: /api/langconnect/user/accessible-graphs (Next.js)
       - Calls /mirror/graphs + this endpoint to provide combined discovery
       - See: apps/web/src/app/api/langconnect/user/accessible-graphs/route.ts:130

    WHY SEPARATE FROM GRAPHS:
    - Independent caching with optimized TTL (3 minutes vs 5 minutes)
      * Assistants update more frequently than graph templates
      * Shorter TTL ensures fresher data for user-created assistants
    - ETag-based HTTP cache for bandwidth efficiency
    - Allows future direct queries without graph data overhead
    - Clean separation of concerns (agents vs agent instances)

    CACHING STRATEGY:
    - ETag generation based on assistants_version from cache_state table
    - Returns 304 Not Modified when client ETag matches
    - Cache-Control: private, max-age=180 (3 minutes)
    - Incremental sync before listing to reduce post-create flicker
    - Versioning incremented on assistant mutations

    PERMISSIONS:
    - Filters by assistant_permissions table (owner/viewer access)
    - Includes owner metadata for UI display
    - Counts owned vs shared assistants for UI metrics
    - Respects retired graphs (hides assistants from retired templates)
    - Service accounts see all assistants

    Serves from assistants_mirror joined with permissions and presentation metadata.
    """
    try:
        log.info(f"Listing assistants from mirror for {actor.actor_type}:{actor.identity}")
        
        # ========================================================================
        # INCREMENTAL SYNC: Reduce flicker for newly-created assistants
        # ========================================================================
        # Pre-sync ensures the mirror is current before listing, reducing the
        # chance that a user sees stale data immediately after creating an assistant.
        # ========================================================================

        # Ensure mirrors are current for the calling user to avoid flicker after create
        try:
            if actor.actor_type != "service":
                user_token = actor.access_token if hasattr(actor, "access_token") else None
                await sync_service.sync_assistants_incremental(user_token=user_token)
        except Exception as e:
            log.warning(f"Incremental sync before listing assistants failed (continuing): {e}")

        async with get_db_connection() as conn:
            # ========================================================================
            # ETAG CACHING: Independent cache for assistants (3min TTL)
            # ========================================================================
            # This endpoint has its own cache version separate from graphs because
            # user-created assistants update more frequently than graph templates.
            # Shorter TTL (3min vs 5min) ensures fresher data.
            # ========================================================================

            # Get cache state for ETag
            cache_state = await conn.fetchrow(
                "SELECT assistants_version FROM langconnect.cache_state WHERE id = 1"
            )
            assistants_version = cache_state["assistants_version"] if cache_state else 1

            # Generate ETag from version
            etag = f'"assistants-v{assistants_version}"'

            # Check if client has current version
            if if_none_match == etag:
                response.status_code = 304
                return {}

            # Set ETag header
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=180"  # 3 minutes soft cache
            
            include_retired = False
            if actor.actor_type == "user":
                user_role = await GraphPermissionsManager.get_user_role(actor.identity)
                include_retired = user_role == "dev_admin"

            if actor.actor_type == "service":
                # Service accounts see all assistants
                assistants_query = """
                    SELECT
                        am.assistant_id,
                        am.graph_id,
                        am.name,
                        am.description,
                        am.tags,
                        am.config,
                        am.metadata,
                        am.version,
                        am.langgraph_created_at,
                        am.langgraph_updated_at,
                        'admin' as permission_level,
                        NULL::text as owner_id,
                        NULL::text as owner_display_name
                    FROM langconnect.assistants_mirror am
                    LEFT JOIN langconnect.admin_retired_graphs rg ON rg.graph_id = am.graph_id AND rg.status = 'marked'
                    WHERE ($1::boolean OR rg.graph_id IS NULL)
                    ORDER BY am.langgraph_updated_at DESC
                """
                assistants = await conn.fetch(assistants_query, include_retired)
            else:
                # Regular users see only assistants they have permission for
                assistants_query = """
                    SELECT
                        am.assistant_id,
                        am.graph_id,
                        am.name,
                        am.description,
                        am.tags,
                        am.config,
                        am.metadata,
                        am.version,
                        am.langgraph_created_at,
                        am.langgraph_updated_at,
                        ap.permission_level,
                        owner_perm.user_id as owner_id,
                        owner_ur.display_name as owner_display_name
                    FROM langconnect.assistants_mirror am
                    LEFT JOIN langconnect.admin_retired_graphs rg ON rg.graph_id = am.graph_id AND rg.status = 'marked'
                    JOIN langconnect.assistant_permissions ap ON am.assistant_id = ap.assistant_id
                    LEFT JOIN langconnect.assistant_permissions owner_perm ON am.assistant_id = owner_perm.assistant_id AND owner_perm.permission_level = 'owner'
                    LEFT JOIN langconnect.user_roles owner_ur ON owner_perm.user_id = owner_ur.user_id
                    WHERE ap.user_id = $1 AND ($2::boolean OR rg.graph_id IS NULL)
                    ORDER BY am.langgraph_updated_at DESC
                """
                assistants = await conn.fetch(assistants_query, actor.identity, include_retired)
            
            # Format response
            assistants_list = []
            owned_count = 0
            shared_count = 0

            for assistant in assistants:
                # Calculate allowed actions for this assistant
                if actor.actor_type == "service":
                    # Service accounts get full admin access
                    allowed_actions = ["view", "chat", "edit", "delete", "share", "manage_access"]
                else:
                    # Regular users: calculate based on permissions and metadata
                    allowed_actions = await PermissionService.get_allowed_actions(
                        user_id=actor.identity,
                        resource_type="assistant",
                        resource_id=str(assistant["assistant_id"]),
                        resource_metadata={"metadata": assistant["metadata"]}  # Pass metadata to avoid extra DB query
                    )

                assistant_info = {
                    "assistant_id": str(assistant["assistant_id"]),
                    "graph_id": assistant["graph_id"],
                    "name": assistant["name"],
                    "description": assistant["description"],
                    "tags": assistant["tags"] or [],
                    "config": assistant["config"],
                    "metadata": assistant["metadata"],
                    "version": assistant["version"],
                    "permission_level": assistant["permission_level"],
                    "owner_id": assistant["owner_id"],
                    "owner_display_name": assistant["owner_display_name"],
                    "available": True,
                    "created_at": assistant["langgraph_created_at"].isoformat(),
                    "updated_at": assistant["langgraph_updated_at"].isoformat(),
                    "allowed_actions": allowed_actions
                }
                assistants_list.append(assistant_info)

                if assistant["permission_level"] == "owner":
                    owned_count += 1
                else:
                    shared_count += 1
            
            log.info(f"Listed {len(assistants_list)} assistants from mirror for {actor.actor_type}:{actor.identity}")
            
            return {
                "assistants": assistants_list,
                "total_count": len(assistants_list),
                "owned_count": owned_count,
                "shared_count": shared_count,
                "assistants_version": assistants_version
            }
            
    except Exception as e:
        log.error(f"Failed to list assistants from mirror: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list assistants from mirror: {str(e)}"
        )


@router.get("/assistants/{assistant_id}")
async def get_assistant_from_mirror(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Get assistant details from mirror with permission metadata.
    """
    try:
        log.info(f"Getting assistant {assistant_id} from mirror for {actor.actor_type}:{actor.identity}")
        
        # Attempt a targeted sync for this assistant first to avoid immediate 404 after create
        try:
            user_token = actor.access_token if hasattr(actor, "access_token") else None
            await sync_service.sync_assistant(assistant_id, user_token=user_token)
        except Exception as e:
            log.warning(f"Targeted assistant sync before read failed (continuing): {e}")

        async with get_db_connection() as conn:
            if actor.actor_type == "service":
                # Service accounts can see any assistant
                assistant_query = """
                    SELECT
                        am.assistant_id,
                        am.graph_id,
                        am.name,
                        am.description,
                        am.tags,
                        am.config,
                        am.metadata,
                        am.context,
                        am.version,
                        am.langgraph_created_at,
                        am.langgraph_updated_at,
                        'admin' as user_permission_level,
                        owner_perm.user_id as owner_id,
                        owner_ur.display_name as owner_display_name
                    FROM langconnect.assistants_mirror am
                    LEFT JOIN langconnect.assistant_permissions owner_perm ON am.assistant_id = owner_perm.assistant_id AND owner_perm.permission_level = 'owner'
                    LEFT JOIN langconnect.user_roles owner_ur ON owner_perm.user_id = owner_ur.user_id
                    WHERE am.assistant_id = $1
                """
                assistant = await conn.fetchrow(assistant_query, UUID(assistant_id))
            else:
                # Regular users need permission
                assistant_query = """
                    SELECT
                        am.assistant_id,
                        am.graph_id,
                        am.name,
                        am.description,
                        am.tags,
                        am.config,
                        am.metadata,
                        am.context,
                        am.version,
                        am.langgraph_created_at,
                        am.langgraph_updated_at,
                        ap.permission_level as user_permission_level,
                        owner_perm.user_id as owner_id,
                        owner_ur.display_name as owner_display_name
                    FROM langconnect.assistants_mirror am
                    JOIN langconnect.assistant_permissions ap ON am.assistant_id = ap.assistant_id
                    LEFT JOIN langconnect.assistant_permissions owner_perm ON am.assistant_id = owner_perm.assistant_id AND owner_perm.permission_level = 'owner'
                    LEFT JOIN langconnect.user_roles owner_ur ON owner_perm.user_id = owner_ur.user_id
                    WHERE am.assistant_id = $1 AND ap.user_id = $2
                """
                assistant = await conn.fetchrow(assistant_query, UUID(assistant_id), actor.identity)
            
            if not assistant:
                raise HTTPException(
                    status_code=404,
                    detail="Assistant not found or no permission"
                )
            
            # Get permissions list for owners/admins
            permissions = []
            if assistant["user_permission_level"] in ["owner", "admin"] or actor.actor_type == "service":
                permissions_data = await AssistantPermissionsManager.get_assistant_permissions(assistant_id)
                permissions = [
                    {
                        "user_id": perm["user_id"],
                        "email": perm["email"] or "Unknown",
                        "display_name": perm["display_name"] or "Unknown User",
                        "permission_level": perm["permission_level"],
                        "granted_by": perm["granted_by"],
                        "granted_at": perm["created_at"].isoformat() if perm["created_at"] else "Unknown"
                    }
                    for perm in permissions_data
                ]

            # Calculate allowed actions for this assistant
            if actor.actor_type == "service":
                # Service accounts get full admin access
                allowed_actions = ["view", "chat", "edit", "delete", "share", "manage_access"]
            else:
                # Regular users: calculate based on permissions and metadata
                allowed_actions = await PermissionService.get_allowed_actions(
                    user_id=actor.identity,
                    resource_type="assistant",
                    resource_id=assistant_id,
                    resource_metadata={"metadata": assistant["metadata"]}  # Pass metadata to avoid extra DB query
                )

            # Set cache headers
            response.headers["Cache-Control"] = "private, max-age=180"

            return {
                "assistant_id": str(assistant["assistant_id"]),
                "graph_id": assistant["graph_id"],
                "name": assistant["name"],
                "description": assistant["description"],
                "tags": assistant["tags"] or [],
                "config": assistant["config"],
                "metadata": assistant["metadata"],
                "context": assistant["context"],
                "version": assistant["version"],
                "user_permission_level": assistant["user_permission_level"],
                "owner_id": assistant["owner_id"],
                "owner_display_name": assistant["owner_display_name"],
                "created_at": assistant["langgraph_created_at"].isoformat(),
                "updated_at": assistant["langgraph_updated_at"].isoformat(),
                "permissions": permissions,
                "allowed_actions": allowed_actions
            }
            
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get assistant from mirror: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get assistant from mirror: {str(e)}"
        )


@router.get("/assistants/{assistant_id}/schemas")
async def get_assistant_schemas_from_mirror(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    if_none_match: Optional[str] = Header(None, alias="if-none-match")
) -> Dict[str, Any]:
    """
    Get assistant schemas from mirror with ETag support.
    
    This replaces direct LangGraph schema calls for consistent, fast reads.
    """
    try:
        log.info(f"Getting schemas for assistant {assistant_id} from mirror")
        
        # Check user permission first
        if actor.actor_type != "service":
            user_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if not user_permission:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this assistant"
                )
        
        async with get_db_connection() as conn:
            # Get schemas with ETag
            schemas_query = """
                SELECT 
                    input_schema,
                    config_schema,
                    state_schema,
                    schema_etag,
                    last_fetched_at
                FROM langconnect.assistant_schemas
                WHERE assistant_id = $1
            """
            schemas = await conn.fetchrow(schemas_query, UUID(assistant_id))
            
            if not schemas:
                # If no cached schemas, synchronously attempt to populate them
                log.warning(f"No cached schemas for assistant {assistant_id}. Attempting synchronous sync...")

                try:
                    # Prefer user-scoped sync so user-created assistants are visible
                    user_token = actor.access_token if hasattr(actor, "access_token") else None
                    sync_service = get_sync_service()

                    # Ensure assistant is mirrored first (FK requirement)
                    await sync_service.sync_assistant(assistant_id, user_token=user_token)
                    # Then fetch and cache schemas
                    await sync_service.sync_assistant_schemas(assistant_id, user_token=user_token)

                    # Re-read cached schemas
                    schemas = await conn.fetchrow(schemas_query, UUID(assistant_id))
                except Exception as sync_error:
                    log.error(f"Synchronous schema sync failed for {assistant_id}: {sync_error}")

                if not schemas:
                    # Still not ready - return 202 Accepted with Retry-After to signal warming state
                    response.status_code = 202
                    response.headers["Retry-After"] = "1"
                    return {
                        "warming": True,
                        "detail": "Schemas are being prepared, please retry shortly"
                    }
            
            # Check ETag
            etag = f'"{schemas["schema_etag"]}"'
            if if_none_match == etag:
                response.status_code = 304
                return {}
            
            # Set cache headers
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=1800"  # 30 minutes
            
            # Get cache version for client
            cache_state = await conn.fetchrow(
                "SELECT schemas_version FROM langconnect.cache_state WHERE id = 1"
            )
            schemas_version = cache_state["schemas_version"] if cache_state else 1
            
            return {
                "input_schema": schemas["input_schema"],
                "config_schema": schemas["config_schema"],
                "state_schema": schemas["state_schema"],
                "last_fetched_at": schemas["last_fetched_at"].isoformat(),
                "schemas_version": schemas_version
            }
            
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get schemas from mirror: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get schemas from mirror: {str(e)}"
        )


@router.get("/graphs/{graph_id}/schemas")
async def get_graph_schemas_from_mirror(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    if_none_match: Optional[str] = Header(None, alias="if-none-match")
) -> Dict[str, Any]:
    """
    Get graph template schemas from mirror with ETag support.

    This returns the configuration schema for creating new agents from a graph template.
    Requires graph permission (admin or access).
    """
    try:
        log.info(f"Getting schemas for graph {graph_id} from mirror")

        # Check user permission first
        if actor.actor_type != "service":
            has_permission = await GraphPermissionsManager.has_graph_permission(
                actor.identity, graph_id, "access"
            )
            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to access this graph"
                )

        async with get_db_connection() as conn:
            # Get schemas with ETag
            schemas_query = """
                SELECT
                    input_schema,
                    config_schema,
                    state_schema,
                    schema_etag,
                    last_fetched_at
                FROM langconnect.graph_schemas
                WHERE graph_id = $1
            """
            schemas = await conn.fetchrow(schemas_query, graph_id)

            if not schemas:
                # If no cached schemas, synchronously attempt to populate them
                log.warning(f"No cached schemas for graph {graph_id}. Attempting synchronous sync...")

                try:
                    # Use sync service to populate graph schemas
                    user_token = actor.access_token if hasattr(actor, "access_token") else None
                    sync_service = get_sync_service()

                    # Sync the graph and its schemas
                    await sync_service.sync_graph(graph_id, user_token=user_token)

                    # Re-read cached schemas
                    schemas = await conn.fetchrow(schemas_query, graph_id)
                except Exception as sync_error:
                    log.error(f"Synchronous schema sync failed for graph {graph_id}: {sync_error}")

                if not schemas:
                    # Still not ready - return 202 Accepted with Retry-After
                    response.status_code = 202
                    response.headers["Retry-After"] = "1"
                    return {
                        "warming": True,
                        "detail": "Graph schemas are being prepared, please retry shortly"
                    }

            # Check ETag
            etag = f'"{schemas["schema_etag"]}"'
            if if_none_match == etag:
                response.status_code = 304
                return {}

            # Set cache headers
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=3600"  # 1 hour (graph schemas change rarely)

            # Get cache version for client
            cache_state = await conn.fetchrow(
                "SELECT graph_schemas_version FROM langconnect.cache_state WHERE id = 1"
            )
            graph_schemas_version = cache_state["graph_schemas_version"] if cache_state else 1

            return {
                "input_schema": schemas["input_schema"],
                "config_schema": schemas["config_schema"],
                "state_schema": schemas["state_schema"],
                "last_fetched_at": schemas["last_fetched_at"].isoformat(),
                "graph_schemas_version": graph_schemas_version
            }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get graph schemas from mirror: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get graph schemas from mirror: {str(e)}"
        )


@router.get("/threads")
async def list_threads_from_mirror(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    response: Response,
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)],
    assistant_id: Optional[str] = None,
    graph_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    List threads from mirror filtered by user and optional assistant/graph.
    
    This provides observability into thread usage without storing full messages.
    """
    try:
        log.info(
            f"[threads:list] actor={actor.actor_type}:{actor.identity} assistant_id={assistant_id} graph_id={graph_id} limit={limit} offset={offset}"
        )
        
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access thread endpoints"
            )
        
        # Ensure mirrors are warm for this user to avoid empty results immediately after create
        try:
            user_token = actor.access_token if hasattr(actor, "access_token") else None
            if assistant_id:
                await sync_service.sync_assistant(assistant_id, user_token=user_token)
        except Exception as e:
            log.debug(f"[threads:list] pre-sync skipped error={e}")

        async with get_db_connection() as conn:
            # Build query with filters
            where_clauses = ["tm.user_id = $1"]
            params = [actor.identity]
            param_count = 1
            
            if assistant_id:
                param_count += 1
                where_clauses.append(f"tm.assistant_id = ${param_count}")
                params.append(UUID(assistant_id))
            
            if graph_id:
                param_count += 1
                where_clauses.append(f"tm.graph_id = ${param_count}")
                params.append(graph_id)
            
            # Snapshot params for filters (used by count query)
            params_filters = list(params)
            
            # Add limit and offset to the data query only
            param_count += 1
            limit_clause = f"LIMIT ${param_count}"
            params.append(limit)
            
            param_count += 1
            offset_clause = f"OFFSET ${param_count}"
            params.append(offset)
            
            threads_query = f"""
                SELECT 
                    tm.thread_id,
                    tm.assistant_id,
                    tm.graph_id,
                    tm.name,
                    tm.summary,
                    tm.status,
                    tm.last_message_at,
                    tm.langgraph_created_at,
                    tm.langgraph_updated_at,
                    am.name as assistant_name
                FROM langconnect.threads_mirror tm
                LEFT JOIN langconnect.assistants_mirror am ON tm.assistant_id = am.assistant_id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY tm.langgraph_updated_at DESC NULLS LAST, tm.langgraph_created_at DESC
                {limit_clause} {offset_clause}
            """
            
            threads = await conn.fetch(threads_query, *params)
            
            # Get total count for pagination
            # Build count query without LIMIT/OFFSET using only filter params
            count_query = f"""
                SELECT COUNT(*) 
                FROM langconnect.threads_mirror tm
                WHERE {' AND '.join(where_clauses)}
            """
            total_count = await conn.fetchval(count_query, *params_filters)
            
            # Get cache version
            cache_state = await conn.fetchrow(
                "SELECT threads_version FROM langconnect.cache_state WHERE id = 1"
            )
            threads_version = cache_state["threads_version"] if cache_state else 1
            
            # Format response
            threads_list = []
            for thread in threads:
                threads_list.append({
                    "thread_id": str(thread["thread_id"]),
                    "assistant_id": str(thread["assistant_id"]) if thread["assistant_id"] else None,
                    "graph_id": thread["graph_id"],
                    "name": thread["name"],
                    "summary": thread["summary"],
                    "status": thread["status"],
                    "assistant_name": thread["assistant_name"],
                    "last_message_at": thread["last_message_at"].isoformat() if thread["last_message_at"] else None,
                    "created_at": thread["langgraph_created_at"].isoformat(),
                    "updated_at": thread["langgraph_updated_at"].isoformat() if thread["langgraph_updated_at"] else None
                })
            
            response.headers["Cache-Control"] = "private, max-age=60"  # 1 minute for threads
            
            result = {
                "threads": threads_list,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "threads_version": threads_version
            }
            log.info(
                f"[threads:list] actor={actor.identity} returned={len(threads_list)} total={total_count} version={threads_version}"
            )
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[threads:list] error={str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list threads from mirror: {str(e)}"
        )


@router.post("/threads/touch")
async def touch_thread_in_mirror(
    body: Dict[str, Any],
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Upsert a thread record in the mirror for the current user.

    Expected body fields:
    - thread_id (required, UUID string)
    - assistant_id (optional, UUID string)
    - graph_id (optional, string)
    - status (optional, string)
    - name_if_absent (optional, string) -> will only be set when name is NULL
    - last_message_at (optional, ISO timestamp) -> defaults to NOW()
    """
    try:
        if actor.actor_type != "user":
            raise HTTPException(status_code=403, detail="Only users can modify thread mirrors")

        thread_id_raw = body.get("thread_id")
        if not thread_id_raw:
            raise HTTPException(status_code=400, detail="thread_id is required")

        assistant_id_raw = body.get("assistant_id")
        graph_id = body.get("graph_id")
        status = body.get("status")
        name_if_absent = body.get("name_if_absent")
        last_message_at_raw = body.get("last_message_at")

        # Parse values
        thread_id = UUID(thread_id_raw)
        assistant_id = UUID(assistant_id_raw) if assistant_id_raw else None

        # Parse last_message_at if provided
        last_message_at = None
        if last_message_at_raw:
            try:
                from datetime import datetime
                last_message_at = datetime.fromisoformat(last_message_at_raw)
            except Exception:
                last_message_at = None

        async with get_db_connection() as conn:
            # Determine existing name; set name only if currently NULL
            existing = await conn.fetchrow(
                "SELECT name FROM langconnect.threads_mirror WHERE thread_id = $1",
                thread_id,
            )
            effective_name = existing["name"] if existing else None
            if not effective_name and name_if_absent:
                effective_name = name_if_absent

            # Ensure assistant exists in mirror (for graph derivation)
            if assistant_id is not None:
                try:
                    user_token = actor.access_token if hasattr(actor, "access_token") else None
                    await sync_service.sync_assistant(str(assistant_id), user_token=user_token)
                except Exception as e:
                    log.debug(f"[threads:touch] assistant sync skipped error={e}")

            # If graph_id not supplied but assistant_id is, derive from assistants_mirror
            derived_graph_id = graph_id
            if not derived_graph_id and assistant_id is not None:
                graph_row = await conn.fetchrow(
                    "SELECT graph_id FROM langconnect.assistants_mirror WHERE assistant_id = $1",
                    assistant_id,
                )
                if graph_row:
                    derived_graph_id = graph_row["graph_id"]

            # Provide sane defaults for created/updated timestamps when we do not yet have LG data
            # Use NOW() for both; later reconciliation can overwrite
            log.info(
                f"[threads:touch] actor={actor.identity} thread_id={thread_id} assistant_id={assistant_id} graph_id={derived_graph_id} name_if_absent={(name_if_absent[:60]+'...') if name_if_absent and len(name_if_absent)>60 else name_if_absent} status={status} last_message_at={last_message_at}"
            )
            await conn.execute(
                """
                SELECT langconnect.upsert_thread_mirror(
                    $1, $2, $3, $4, $5, $6, $7, NOW(), NOW()
                )
                """,
                thread_id,
                assistant_id,
                derived_graph_id,
                actor.identity,
                effective_name,
                status,
                last_message_at,
            )

            # Return current threads_version for client cache invalidation
            cache_state = await conn.fetchrow(
                "SELECT threads_version FROM langconnect.cache_state WHERE id = 1"
            )
            threads_version = cache_state["threads_version"] if cache_state else 1

            result = {
                "thread_id": str(thread_id),
                "threads_version": threads_version,
                "touched": True,
            }
            log.info(f"[threads:touch] upserted thread_id={thread_id} version={threads_version}")
            return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[threads:touch] error={e}")
        raise HTTPException(status_code=500, detail=f"Failed to touch thread: {str(e)}")


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> Dict[str, Any]:
    """
    Delete a thread in LangGraph and then remove it from the mirror.
    Also deletes any associated chat images from storage.

    Handles 404 gracefully: if the thread doesn't exist in LangGraph (already deleted
    or never existed), we still clean up the mirror entry to maintain consistency.
    """
    try:
        if actor.actor_type != "user":
            raise HTTPException(status_code=403, detail="Only users can delete threads")

        # Delete associated chat images from storage
        # This is done before deleting the thread to ensure we have the user_id
        from langconnect.services.storage_service import storage_service
        try:
            deleted_count = await storage_service.delete_thread_images(
                user_id=actor.identity,
                thread_id=thread_id
            )
            if deleted_count > 0:
                log.info(f"Deleted {deleted_count} images for thread {thread_id}")
        except Exception as storage_error:
            # Log but don't fail the entire deletion if storage cleanup fails
            log.warning(f"Failed to delete storage images for thread {thread_id}: {storage_error}")

        # Delete upstream in LangGraph first (user-scoped)
        # Handle 404 gracefully - thread may already be deleted from LangGraph
        user_token = actor.access_token if hasattr(actor, "access_token") else None
        try:
            await langgraph_service.delete_thread(thread_id, user_token=user_token)
            log.info(f"Deleted thread {thread_id} from LangGraph")
        except RuntimeError as e:
            # Check if this is a 404 error (thread doesn't exist in LangGraph)
            error_message = str(e).lower()
            if "404" in error_message or "not found" in error_message:
                log.info(f"Thread {thread_id} not found in LangGraph (404) - proceeding with mirror cleanup")
            else:
                # Re-raise other errors (500, 403, network issues, etc.)
                raise

        # Remove from mirror and bump version
        async with get_db_connection() as conn:
            await conn.execute(
                "DELETE FROM langconnect.threads_mirror WHERE thread_id = $1",
                UUID(thread_id),
            )
            await conn.execute(
                "SELECT langconnect.increment_cache_version('threads')"
            )

            cache_state = await conn.fetchrow(
                "SELECT threads_version FROM langconnect.cache_state WHERE id = 1"
            )
            threads_version = cache_state["threads_version"] if cache_state else 1

        log.info(f"Successfully deleted thread {thread_id} from mirror")
        return {"success": True, "thread_id": thread_id, "threads_version": threads_version}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to delete thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete thread: {str(e)}")


@router.patch("/threads/{thread_id}/rename")
async def rename_thread_in_mirror(
    thread_id: str,
    new_name: Annotated[str, Body(embed=True)],
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    db_pool: Annotated[asyncpg.Pool, Depends(get_db_pool)]
) -> Dict[str, Any]:
    """
    Rename a thread in the mirror.
    
    Only the thread owner can rename their threads.
    """
    try:
        log.info(f"[threads:rename] actor={actor.identity} thread_id={thread_id} new_name={new_name[:50]}...")
        
        # Validate new name
        if not new_name or not new_name.strip():
            raise HTTPException(status_code=400, detail="Thread name cannot be empty")
        
        new_name = new_name.strip()[:100]  # Limit to 100 chars
        
        async with db_pool.acquire() as conn:
            # Check if thread exists and user owns it
            existing = await conn.fetchrow(
                "SELECT thread_id, user_id, name FROM langconnect.threads_mirror WHERE thread_id = $1",
                thread_id
            )
            
            if not existing:
                raise HTTPException(status_code=404, detail="Thread not found")
            
            # Permission check - only thread owner can rename
            if str(existing["user_id"]) != actor.identity:
                raise HTTPException(status_code=403, detail="You can only rename your own threads")
            
            # Update the name
            await conn.execute(
                """
                UPDATE langconnect.threads_mirror 
                SET name = $2, mirror_updated_at = NOW(), updated_at = NOW()
                WHERE thread_id = $1
                """,
                thread_id, new_name
            )
            
            # Increment cache version
            await conn.execute(
                "SELECT langconnect.increment_cache_version('threads')"
            )
            
            cache_state = await conn.fetchrow(
                "SELECT threads_version FROM langconnect.cache_state WHERE id = 1"
            )
            threads_version = cache_state["threads_version"] if cache_state else 1
            
        log.info(f"[threads:rename] Successfully renamed thread {thread_id} to '{new_name}' for user {actor.identity}")
        
        return {
            "success": True, 
            "thread_id": thread_id, 
            "new_name": new_name,
            "threads_version": threads_version
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to rename thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rename thread: {str(e)}")


@router.post("/sync/assistant/{assistant_id}")
async def trigger_assistant_sync(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Manually trigger sync for a specific assistant.
    
    Useful after mutations or when debugging sync issues.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger manual sync"
                )
        
        # Prefer user-scoped sync when caller is a user
        user_token = actor.access_token if hasattr(actor, "access_token") else None
        success = await sync_service.sync_assistant(assistant_id, user_token=user_token)
        
        return {
            "assistant_id": assistant_id,
            "synced": success,
            "message": "Assistant sync completed" if success else "Assistant sync failed or unchanged"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to trigger assistant sync: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger assistant sync: {str(e)}"
        )


@router.post("/sync/graph/{graph_id}")
async def trigger_graph_sync(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Manually trigger sync for all assistants in a specific graph.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger manual sync"
                )
        
        user_token = actor.access_token if hasattr(actor, "access_token") else None
        stats = await sync_service.sync_graph(graph_id, user_token=user_token)
        
        return {
            "graph_id": graph_id,
            "sync_stats": stats,
            "message": f"Graph sync completed for {graph_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to trigger graph sync: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger graph sync: {str(e)}"
        )


@router.post("/sync/full")
async def trigger_full_sync(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Manually trigger full sync of all assistants and graphs.
    
    This is a comprehensive sync operation for admin use.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger full sync"
                )
        
        user_token = actor.access_token if hasattr(actor, "access_token") else None
        stats = await sync_service.sync_all_full(user_token=user_token)
        
        return {
            "sync_stats": stats,
            "message": "Full sync completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to trigger full sync: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger full sync: {str(e)}"
        )


@router.post("/sync/schemas")
async def trigger_schemas_sync(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Manually trigger schema sync for all assistants.
    
    Fetches and caches schemas from LangGraph for fast UI decisions.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger schema sync"
                )
        
        # For full schema sync, prefer admin scope (no user token)
        stats = await sync_service.sync_all_schemas()
        
        return {
            "schema_sync_stats": stats,
            "message": "Schema sync completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Schema sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Schema sync failed: {str(e)}")

@router.post("/sync/schemas/{assistant_id}")
async def trigger_assistant_schema_sync(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Manually trigger schema sync for a specific assistant.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger schema sync"
                )
        
        user_token = actor.access_token if hasattr(actor, "access_token") else None
        updated = await sync_service.sync_assistant_schemas(assistant_id, user_token=user_token)
        
        return {
            "assistant_id": assistant_id,
            "schemas_updated": updated,
            "message": "Schema sync completed" if updated else "Schemas unchanged"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Assistant schema sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Schema sync failed: {str(e)}")

@router.post("/backfill")
async def backfill_mirrors(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    sync_service: Annotated[LangGraphSyncService, Depends(get_sync_service)]
) -> Dict[str, Any]:
    """
    Initial backfill of mirror tables from LangGraph.
    
    This should be run once after migration deployment.
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can trigger backfill"
                )
        
        stats = await sync_service.backfill_mirrors()
        
        return {
            "backfill_stats": stats,
            "message": "Mirror backfill completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to trigger backfill: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger backfill: {str(e)}"
        )
