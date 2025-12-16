"""
Admin-level operations for platform initialization and maintenance.

This module contains admin-only endpoints that are separate from regular user workflows.
These operations are typically performed by dev_admins to set up and maintain the platform.
"""

import json
import logging
import time
from typing import Annotated, Dict, List, Any
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    AdminInitializePlatformRequest,
    AdminInitializePlatformResponse,
    EnhancementResult,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
 
from langconnect.services.langgraph_sync import LangGraphSyncService, get_sync_service
from langconnect.database.permissions import GraphPermissionsManager, AssistantPermissionsManager
from langconnect.database.connection import get_db_connection

# Set up logging
log = logging.getLogger(__name__)

# Create router with proper tags for FastAPI docs
router = APIRouter(
    prefix="/admin",
    tags=["Admin Operations"],
    responses={404: {"description": "Not found"}},
)


# Import the functions from graph_actions.lifecycle
async def enhance_system_metadata(
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """Import from lifecycle module - this will be imported properly"""
    from langconnect.api.graph_actions.lifecycle import enhance_system_metadata as _enhance_system_metadata
    return await _enhance_system_metadata(langgraph_service, actor)


async def apply_permission_inheritance(
    user_id: str,
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """Import from lifecycle module - this will be imported properly"""
    from langconnect.api.graph_actions.lifecycle import apply_permission_inheritance as _apply_permission_inheritance
    return await _apply_permission_inheritance(user_id, langgraph_service, actor)


async def sync_dev_admin_permissions(
    user_id: str,
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """Import from lifecycle module - this will be imported properly"""
    from langconnect.api.graph_actions.lifecycle import sync_dev_admin_permissions as _sync_dev_admin_permissions
    return await _sync_dev_admin_permissions(user_id, langgraph_service, actor)


@router.post("/initialize-platform", response_model=AdminInitializePlatformResponse)
async def initialize_platform(
    request: AdminInitializePlatformRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> AdminInitializePlatformResponse:
    """
    Admin endpoint to initialize the platform.

    This endpoint performs platform initialization:
    - Discovers graphs from LangGraph
    - Populates graph metadata (name, description) from config files
    - Grants graph permissions to all dev_admin users
    - Refreshes all assistant schemas from LangGraph (picks up model changes)

    NOTE: This does NOT create or enhance any assistants. System assistants created
    by LangGraph remain hidden. Only user-created assistants appear in the UI.

    **Authorization:**
    - **Dev Admins**: Can initialize platform
    - **Service Accounts**: Can initialize platform
    - **Regular Users**: 403 Forbidden

    **Options:**
    - **Dry Run**: Preview operations without making changes
    """
    start_time = time.time()
    
    try:
        log.info(f"Admin platform initialization requested by {actor.actor_type}:{actor.identity} (dry_run={request.dry_run})")

        # Step 1: Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can initialize the platform"
                )

        operations_performed = []
        successful_operations = 0
        failed_operations = 0
        warnings = []

        # Step 2: Discover and populate graph metadata
        log.info("Step 1: Discovering graph metadata from LangGraph API")
        try:
            from langconnect.api.graph_actions.discovery_utils import get_all_graph_metadata_from_api

            all_metadata = await get_all_graph_metadata_from_api(langgraph_service)
            log.info(f"Found metadata for {len(all_metadata)} graphs")

            graphs_updated = 0
            graphs_failed = 0
            metadata_errors = []

            if not request.dry_run:
                async with get_db_connection() as conn:
                    for graph_id, metadata in all_metadata.items():
                        try:
                            await conn.execute(
                                """
                                INSERT INTO langconnect.graphs_mirror (graph_id, name, description)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (graph_id) DO UPDATE SET
                                    name = COALESCE(langconnect.graphs_mirror.name, EXCLUDED.name),
                                    description = COALESCE(langconnect.graphs_mirror.description, EXCLUDED.description),
                                    updated_at = NOW()
                                """,
                                graph_id,
                                metadata["name"],
                                metadata["description"]
                            )
                            graphs_updated += 1
                        except Exception as e:
                            graphs_failed += 1
                            metadata_errors.append(f"Failed to populate metadata for {graph_id}: {str(e)}")
                            log.error(f"Failed to populate metadata for {graph_id}: {e}")

                    # Increment graph version to invalidate frontend cache
                    await conn.fetchval("SELECT langconnect.increment_cache_version('graphs')")

            operations_performed.append(EnhancementResult(
                operation="graph_metadata_discovery",
                success=graphs_failed == 0,
                total_enhanced=graphs_updated if not request.dry_run else len(all_metadata),
                failed=graphs_failed,
                message=f"{'Would discover' if request.dry_run else 'Discovered'} metadata for {len(all_metadata)} graphs",
                errors=metadata_errors
            ))

            if graphs_failed == 0:
                successful_operations += 1
            else:
                failed_operations += 1

            log.info(f"Metadata discovery completed: {graphs_updated} graphs updated, {graphs_failed} failed")

        except Exception as e:
            failed_operations += 1
            error_msg = f"Metadata discovery failed: {str(e)}"
            log.error(error_msg)
            warnings.append(error_msg)
            operations_performed.append(EnhancementResult(
                operation="graph_metadata_discovery",
                success=False,
                total_enhanced=0,
                failed=1,
                message="Failed to discover graph metadata",
                errors=[str(e)]
            ))

        # Step 3: Grant graph permissions to all dev_admins
        log.info("Step 2: Granting graph permissions to dev_admins")
        try:
            # Get all dev_admins
            dev_admins = await GraphPermissionsManager.get_all_dev_admins()
            log.info(f"Found {len(dev_admins)} dev_admin users")

            # Get all discovered graphs
            async with get_db_connection() as conn:
                graphs_result = await conn.fetch(
                    "SELECT graph_id FROM langconnect.graphs_mirror ORDER BY graph_id"
                )
                graph_ids = [row["graph_id"] for row in graphs_result]

            log.info(f"Found {len(graph_ids)} graphs to grant permissions for")

            permissions_granted = 0
            permissions_failed = 0
            permission_errors = []

            if not request.dry_run:
                for graph_id in graph_ids:
                    for dev_admin in dev_admins:
                        try:
                            # Always attempt to grant permission (ON CONFLICT will handle duplicates)
                            success = await GraphPermissionsManager.grant_graph_permission(
                                graph_id=graph_id,
                                user_id=dev_admin["user_id"],
                                permission_level="admin",
                                granted_by="system:platform_initialization"
                            )

                            if success:
                                permissions_granted += 1
                                log.info(f"Granted admin permission for graph {graph_id} to dev_admin {dev_admin['email']}")
                            else:
                                permissions_failed += 1
                                permission_errors.append(f"Failed to grant permission for {graph_id} to {dev_admin['email']}")
                        except Exception as e:
                            permissions_failed += 1
                            permission_errors.append(f"Error granting permission for {graph_id} to {dev_admin['email']}: {str(e)}")
                            log.error(f"Error granting permission for {graph_id} to {dev_admin['email']}: {e}")

            operations_performed.append(EnhancementResult(
                operation="dev_admin_graph_permissions",
                success=permissions_failed == 0,
                total_enhanced=permissions_granted if not request.dry_run else len(graph_ids) * len(dev_admins),
                failed=permissions_failed,
                message=f"{'Would grant' if request.dry_run else 'Granted'} {len(graph_ids)} graph permissions to {len(dev_admins)} dev_admins",
                errors=permission_errors
            ))

            if permissions_failed == 0:
                successful_operations += 1
            else:
                failed_operations += 1

            log.info(f"Permission grants completed: {permissions_granted} granted, {permissions_failed} failed")

        except Exception as e:
            failed_operations += 1
            error_msg = f"Permission grants failed: {str(e)}"
            log.error(error_msg)
            warnings.append(error_msg)
            operations_performed.append(EnhancementResult(
                operation="dev_admin_graph_permissions",
                success=False,
                total_enhanced=0,
                failed=1,
                message="Failed to grant graph permissions",
                errors=[str(e)]
            ))

        # Step 4: Refresh all assistant schemas
        # This ensures config schemas reflect current model options after migrations
        if not request.dry_run:
            log.info("Step 4: Refreshing assistant schemas from LangGraph")
            try:
                sync_service = get_sync_service()
                schemas_result = await sync_service.sync_all_schemas()
                schemas_updated = schemas_result.get("updated", 0)
                schemas_total = schemas_result.get("total", 0)
                schemas_errors = schemas_result.get("errors", [])

                operations_performed.append(EnhancementResult(
                    operation="refresh_assistant_schemas",
                    success=len(schemas_errors) == 0,
                    total_enhanced=schemas_updated,
                    failed=len(schemas_errors),
                    message=f"Refreshed {schemas_updated}/{schemas_total} assistant schemas",
                    errors=schemas_errors[:5] if schemas_errors else []  # Limit errors shown
                ))

                if len(schemas_errors) == 0:
                    successful_operations += 1
                else:
                    failed_operations += 1

                log.info(f"Schema refresh completed: {schemas_updated}/{schemas_total} updated, {len(schemas_errors)} errors")

            except Exception as e:
                failed_operations += 1
                error_msg = f"Schema refresh failed: {str(e)}"
                log.error(error_msg)
                warnings.append(error_msg)
                operations_performed.append(EnhancementResult(
                    operation="refresh_assistant_schemas",
                    success=False,
                    total_enhanced=0,
                    failed=1,
                    message="Failed to refresh assistant schemas",
                    errors=[str(e)]
                ))
        else:
            # Dry run - just report what would happen
            operations_performed.append(EnhancementResult(
                operation="refresh_assistant_schemas",
                success=True,
                total_enhanced=0,
                failed=0,
                message="Would refresh all assistant schemas from LangGraph",
                errors=[]
            ))

        # Step 5: Generate summary
        total_operations = len(operations_performed)
        duration_ms = int((time.time() - start_time) * 1000)

        action_word = "would be" if request.dry_run else "were"
        summary_parts = []

        for result in operations_performed:
            if result.total_enhanced > 0:
                summary_parts.append(f"{result.operation}: {result.total_enhanced} operations {action_word} performed")

        summary = f"Platform initialization completed: {', '.join(summary_parts) if summary_parts else 'No operations needed'}"

        log.info(f"Admin platform initialization completed: {successful_operations} successful, {failed_operations} failed operations in {duration_ms}ms")

        return AdminInitializePlatformResponse(
            dry_run=request.dry_run,
            operations_performed=operations_performed,
            total_operations=sum(op.total_enhanced for op in operations_performed),
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            duration_ms=duration_ms,
            warnings=warnings,
            summary=summary
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        log.error(f"Failed to initialize platform: {str(e)}")
        
        
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize platform: {str(e)}"
        )


@router.get("/retired-graphs")
async def list_retired_graphs(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """
    List retired graphs marked by dev admins.
    """
    # Only dev_admins or service accounts
    if actor.actor_type == "user":
        user_role = await GraphPermissionsManager.get_user_role(actor.identity)
        if user_role != "dev_admin":
            raise HTTPException(status_code=403, detail="Only dev_admins can list retired graphs")

    async with get_db_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT graph_id, status, reason, notes, marked_by, marked_at, pruned_by, pruned_at
            FROM langconnect.admin_retired_graphs
            ORDER BY marked_at DESC
            """
        )
        return {
            "retired_graphs": [
                {
                    "graph_id": r["graph_id"],
                    "status": r["status"],
                    "reason": r["reason"],
                    "notes": r["notes"],
                    "marked_by": str(r["marked_by"]) if r["marked_by"] else None,
                    "marked_at": r["marked_at"].isoformat() if r["marked_at"] else None,
                    "pruned_by": str(r["pruned_by"]) if r["pruned_by"] else None,
                    "pruned_at": r["pruned_at"].isoformat() if r["pruned_at"] else None,
                }
                for r in rows
            ]
        }


@router.post("/retired-graphs/{graph_id}/retire")
async def retire_graph(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    body: Dict[str, Any] | None = None,
):
    """
    Mark a graph as retired (unavailable). No automatic deletes.
    Idempotent: upsert row with status 'marked'.
    """
    # Only dev_admins or service accounts
    if actor.actor_type == "user":
        user_role = await GraphPermissionsManager.get_user_role(actor.identity)
        if user_role != "dev_admin":
            raise HTTPException(status_code=403, detail="Only dev_admins can retire graphs")

    reason = (body or {}).get("reason")
    notes = (body or {}).get("notes")

    async with get_db_connection() as conn:
        await conn.execute(
            """
            INSERT INTO langconnect.admin_retired_graphs (graph_id, status, reason, notes, marked_by)
            VALUES ($1, 'marked', $2, $3, $4)
            ON CONFLICT (graph_id) DO UPDATE SET
                status = 'marked',
                reason = EXCLUDED.reason,
                notes = EXCLUDED.notes,
                marked_by = EXCLUDED.marked_by,
                marked_at = NOW(),
                updated_at = NOW()
            """,
            graph_id,
            reason,
            notes,
            UUID(actor.identity) if actor.actor_type == "user" else None,
        )
        # Bump versions so clients refresh
        await conn.fetchval("SELECT langconnect.increment_cache_version('graphs')")
        await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")

    return {"graph_id": graph_id, "status": "marked"}


@router.post("/retired-graphs/{graph_id}/unretire")
async def unretire_graph(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """
    Remove retired status for a graph.
    """
    if actor.actor_type == "user":
        user_role = await GraphPermissionsManager.get_user_role(actor.identity)
        if user_role != "dev_admin":
            raise HTTPException(status_code=403, detail="Only dev_admins can unretire graphs")

    async with get_db_connection() as conn:
        await conn.execute(
            "DELETE FROM langconnect.admin_retired_graphs WHERE graph_id = $1",
            graph_id,
        )
        await conn.fetchval("SELECT langconnect.increment_cache_version('graphs')")
        await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")

    return {"graph_id": graph_id, "status": "active"}


@router.post("/retired-graphs/{graph_id}/prune")
async def prune_retired_graph(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
    body: Dict[str, Any] | None = None,
):
    """
    Manually prune a retired graph:
    - Delete assistants_mirror for this graph (cascades schemas)
    - Delete assistant_permissions for this graph
    - Delete graph_permissions and graphs_mirror row
    - Null out threads_mirror references
    - Mark admin_retired_graphs.status = 'pruned'
    """
    if actor.actor_type == "user":
        user_role = await GraphPermissionsManager.get_user_role(actor.identity)
        if user_role != "dev_admin":
            raise HTTPException(status_code=403, detail="Only dev_admins can prune graphs")

    async with get_db_connection() as conn:
        # 1) Delete all assistants in LangGraph for this graph (covers legacy leftovers)
        try:
            lg_resp = await langgraph_service._make_request(
                "POST",
                "assistants/search",
                data={"graph_id": graph_id, "limit": 1000, "offset": 0},
            )
            langgraph_assistants = (
                lg_resp if isinstance(lg_resp, list) else lg_resp.get("assistants", [])
            )
            for a in langgraph_assistants:
                a_id = a.get("assistant_id")
                if not a_id:
                    continue
                try:
                    await langgraph_service._make_request("DELETE", f"assistants/{a_id}")
                except Exception as e:
                    log.warning(f"Failed to delete assistant {a_id} from LangGraph: {e}")
        except Exception as e:
            log.warning(f"Failed to search/delete LangGraph assistants for graph {graph_id}: {e}")

        # 2) Collect assistant IDs from mirror before deleting them (for any residual cleanup)
        # Collect assistant IDs for this graph
        assistant_ids = await conn.fetch(
            """
            SELECT assistant_id FROM langconnect.assistants_mirror WHERE graph_id = $1
            """,
            graph_id,
        )
        assistant_uuid_list = [row["assistant_id"] for row in assistant_ids]

        # 3) Delete from mirrors (assistants cascades schemas)
        await conn.execute(
            "DELETE FROM langconnect.assistants_mirror WHERE graph_id = $1",
            graph_id,
        )

        # 4) Permissions cleanup (use assistants_mirror for graph linkage)
        if assistant_uuid_list:
            await conn.execute(
                "DELETE FROM langconnect.assistant_permissions WHERE assistant_id = ANY($1)",
                [str(a) for a in assistant_uuid_list],
            )

        await conn.execute(
            "DELETE FROM langconnect.graph_permissions WHERE graph_id = $1",
            graph_id,
        )

        # 5) Null references in threads mirror
        await conn.execute(
            "UPDATE langconnect.threads_mirror SET assistant_id = NULL WHERE graph_id = $1",
            graph_id,
        )
        await conn.execute(
            "UPDATE langconnect.threads_mirror SET graph_id = NULL WHERE graph_id = $1",
            graph_id,
        )

        # 6) Remove graph from mirror
        await conn.execute(
            "DELETE FROM langconnect.graphs_mirror WHERE graph_id = $1",
            graph_id,
        )

        # 7) Mark admin_retired_graphs as pruned
        await conn.execute(
            """
            INSERT INTO langconnect.admin_retired_graphs (graph_id, status, pruned_by, pruned_at)
            VALUES ($1, 'pruned', $2, NOW())
            ON CONFLICT (graph_id) DO UPDATE SET status = 'pruned', pruned_by = EXCLUDED.pruned_by, pruned_at = NOW(), updated_at = NOW()
            """,
            graph_id,
            UUID(actor.identity) if actor.actor_type == "user" else None,
        )

        # 8) Bump cache versions
        await conn.fetchval("SELECT langconnect.increment_cache_version('graphs')")
        await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
        await conn.fetchval("SELECT langconnect.increment_cache_version('schemas')")
        await conn.fetchval("SELECT langconnect.increment_cache_version('threads')")

    return {"graph_id": graph_id, "status": "pruned"}

@router.post("/backfill-mirrors")
async def backfill_mirrors(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> Dict[str, Any]:
    """
    Admin endpoint to backfill mirror tables from current LangGraph state.
    
    This should be run once after migration deployment to populate the mirrors.
    
    **Authorization:**
    - **Dev Admins**: Can backfill mirrors
    - **Service Accounts**: Can backfill mirrors
    - **Regular Users**: 403 Forbidden
    """
    start_time = time.time()
    
    try:
        log.info(f"Mirror backfill requested by {actor.actor_type}:{actor.identity}")
        
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can backfill mirrors"
                )
        
        # Create sync service and run backfill
        sync_service = get_sync_service()
        stats = await sync_service.backfill_mirrors()
        
        
        
        return {
            "backfill_stats": stats,
            "message": "Mirror backfill completed successfully",
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to backfill mirrors: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to backfill mirrors: {str(e)}"
        )


@router.get("/mirror-status")
async def get_mirror_status(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> Dict[str, Any]:
    """
    Get status of mirror tables for debugging and monitoring.
    
    **Authorization:**
    - **Dev Admins**: Can view mirror status
    - **Service Accounts**: Can view mirror status
    - **Regular Users**: 403 Forbidden
    """
    try:
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can view mirror status"
                )
        
        # Get mirror statistics
        from langconnect.database.connection import get_db_connection
        
        async with get_db_connection() as conn:
            # Count mirror table contents
            graphs_count = await conn.fetchval("SELECT COUNT(*) FROM langconnect.graphs_mirror")
            assistants_count = await conn.fetchval("SELECT COUNT(*) FROM langconnect.assistants_mirror")
            schemas_count = await conn.fetchval("SELECT COUNT(*) FROM langconnect.assistant_schemas")
            threads_count = await conn.fetchval("SELECT COUNT(*) FROM langconnect.threads_mirror")
            
            # Get cache state
            cache_state = await conn.fetchrow(
                """
                SELECT graphs_version, assistants_version, schemas_version, 
                       threads_version, last_synced_at
                FROM langconnect.cache_state WHERE id = 1
                """
            )
            
            # Get some sample data
            recent_assistants = await conn.fetch(
                """
                SELECT assistant_id, name, graph_id, langgraph_updated_at, mirror_updated_at
                FROM langconnect.assistants_mirror
                ORDER BY langgraph_updated_at DESC
                LIMIT 5
                """
            )
        
        return {
            "mirror_counts": {
                "graphs": graphs_count,
                "assistants": assistants_count,
                "schemas": schemas_count,
                "threads": threads_count
            },
            "cache_state": {
                "graphs_version": cache_state["graphs_version"] if cache_state else 0,
                "assistants_version": cache_state["assistants_version"] if cache_state else 0,
                "schemas_version": cache_state["schemas_version"] if cache_state else 0,
                "threads_version": cache_state["threads_version"] if cache_state else 0,
                "last_synced_at": cache_state["last_synced_at"].isoformat() if cache_state and cache_state["last_synced_at"] else None
            },
            "recent_assistants": [
                {
                    "assistant_id": str(a["assistant_id"]),
                    "name": a["name"],
                    "graph_id": a["graph_id"],
                    "langgraph_updated_at": a["langgraph_updated_at"].isoformat(),
                    "mirror_updated_at": a["mirror_updated_at"].isoformat()
                }
                for a in recent_assistants
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get mirror status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get mirror status: {str(e)}"
        )


@router.post("/reverse-sync-assistants")
async def reverse_sync_assistants(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> Dict[str, Any]:
    """
    Admin endpoint to reverse sync assistants from UI database to LangGraph.

    This recreates all assistants in the local LangGraph deployment while preserving
    thread references and permissions. Useful for local development when LangGraph
    state is lost but database state remains.

    **Authorization:**
    - **Dev Admins**: Can reverse sync assistants
    - **Service Accounts**: Can reverse sync assistants
    - **Regular Users**: 403 Forbidden

    **Process:**
    - Fetches all assistants from assistants_mirror table
    - Creates each assistant in LangGraph with same config
    - Updates database references (threads, permissions) to new assistant IDs
    - Preserves all thread history and permission relationships
    """
    start_time = time.time()

    try:
        log.info(f"Reverse sync assistants requested by {actor.actor_type}:{actor.identity}")

        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can reverse sync assistants"
                )

        # Fetch only user-created assistants from database (exclude system template assistants)
        # Template assistants have metadata->>'created_by' = 'system'
        async with get_db_connection() as conn:
            assistants = await conn.fetch(
                """
                SELECT assistant_id, graph_id, name, description, config, metadata
                FROM langconnect.assistants_mirror
                WHERE (metadata->>'created_by' IS NULL OR metadata->>'created_by' != 'system')
                  AND metadata ? 'owner'
                ORDER BY created_at
                """
            )

        total_assistants = len(assistants)
        recreated_count = 0
        failed_count = 0
        failed_assistants = []

        log.info(f"Found {total_assistants} assistants to recreate in LangGraph")

        # Recreate each assistant
        for assistant in assistants:
            old_id = str(assistant["assistant_id"])
            assistant_name = assistant["name"]
            payload = None

            try:
                # Create assistant in LangGraph
                log.info(f"Creating assistant '{assistant_name}' (old ID: {old_id}) in LangGraph")

                # Prepare payload with proper None handling
                payload = {
                    "graph_id": assistant["graph_id"],
                    "name": assistant["name"],
                }

                # Only add optional fields if they have values
                if assistant["description"]:
                    payload["description"] = assistant["description"]

                # Parse config - handle both dict and JSON string
                if assistant["config"]:
                    config_value = assistant["config"]
                    if isinstance(config_value, str):
                        try:
                            payload["config"] = json.loads(config_value)
                        except json.JSONDecodeError:
                            log.error(f"Invalid JSON in config for '{assistant_name}': {config_value[:100]}")
                            raise ValueError(f"Invalid config JSON for assistant '{assistant_name}'")
                    else:
                        payload["config"] = config_value

                # Parse metadata - use robust defensive parsing
                if assistant["metadata"]:
                    from langconnect.utils.metadata_validation import parse_metadata_safe

                    metadata_value = assistant["metadata"]
                    # Use robust parsing to handle all corruption cases
                    parsed_metadata = parse_metadata_safe(metadata_value, "metadata")

                    # Add owner if not present (fallback safety)
                    if "owner" not in parsed_metadata:
                        parsed_metadata["owner"] = str(assistant.get("owner", "unknown"))

                    payload["metadata"] = parsed_metadata
                else:
                    # No metadata in DB - create minimal metadata
                    payload["metadata"] = {"owner": str(assistant.get("owner", "unknown"))}

                # Sanitize payload to prevent corruption propagation
                from langconnect.utils.metadata_validation import sanitize_langgraph_payload
                payload = sanitize_langgraph_payload(payload)

                log.info(f"Payload for '{assistant_name}': graph_id={payload['graph_id']}, name={payload['name']}, has_config={bool(payload.get('config'))}, has_metadata={bool(payload.get('metadata'))}")

                create_response = await langgraph_service._make_request(
                    "POST",
                    "assistants",
                    data=payload
                )

                new_id = create_response["assistant_id"]
                log.info(f"Created assistant '{assistant_name}' with new ID: {new_id}")

                # Update database references in transaction
                async with get_db_connection() as conn:
                    async with conn.transaction():
                        # CRITICAL: Insert new assistant into mirror FIRST to satisfy FK constraints
                        # This must happen before any updates to threads_mirror, assistant_permissions, etc.
                        await conn.execute(
                            """
                            INSERT INTO langconnect.assistants_mirror
                            (assistant_id, graph_id, name, description, config, metadata, context,
                             version, langgraph_created_at, langgraph_updated_at, langgraph_hash, last_seen_at)
                            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, NOW(), NOW(), $9, NOW())
                            """,
                            UUID(new_id),
                            create_response["graph_id"],
                            create_response["name"],
                            create_response.get("description"),
                            json.dumps(create_response.get("config", {})),
                            json.dumps(create_response.get("metadata", {})),
                            json.dumps(create_response.get("context", {})),
                            create_response.get("version", 1),
                            f"reverse-sync-{new_id}"  # langgraph_hash
                        )
                        log.info(f"Inserted new assistant {new_id} into assistants_mirror")

                        # Now update threads to point to new assistant ID (FK constraint satisfied)
                        thread_result = await conn.execute(
                            """
                            UPDATE langconnect.threads_mirror
                            SET assistant_id = $1
                            WHERE assistant_id = $2
                            """,
                            UUID(new_id),
                            UUID(old_id)
                        )
                        # Parse "UPDATE n" to get count
                        thread_updates = int(thread_result.split()[-1]) if thread_result else 0

                        # Update user default assistants
                        default_result = await conn.execute(
                            """
                            UPDATE langconnect.user_default_assistants
                            SET assistant_id = $1
                            WHERE assistant_id = $2
                            """,
                            UUID(new_id),
                            UUID(old_id)
                        )
                        # Parse "UPDATE n" to get count
                        default_updates = int(default_result.split()[-1]) if default_result else 0

                        # Copy permissions with new ID (FK constraint now satisfied)
                        permissions = await conn.fetch(
                            """
                            SELECT user_id, permission_level, granted_by
                            FROM langconnect.assistant_permissions
                            WHERE assistant_id = $1
                            """,
                            UUID(old_id)
                        )

                        # Insert new permissions
                        for perm in permissions:
                            await conn.execute(
                                """
                                INSERT INTO langconnect.assistant_permissions
                                (assistant_id, user_id, permission_level, granted_by)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (assistant_id, user_id) DO UPDATE SET
                                    permission_level = EXCLUDED.permission_level,
                                    updated_at = NOW()
                                """,
                                UUID(new_id),
                                perm["user_id"],
                                perm["permission_level"],
                                perm["granted_by"]
                            )

                        # Delete old assistant record (this cascades to old permissions and schemas)
                        await conn.execute(
                            "DELETE FROM langconnect.assistants_mirror WHERE assistant_id = $1",
                            UUID(old_id)
                        )

                        log.info(
                            f"Updated {thread_updates} threads, {default_updates} defaults, "
                            f"{len(permissions)} permissions for '{assistant_name}'"
                        )

                recreated_count += 1

            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to recreate '{assistant_name}': {str(e)}"
                log.error(error_msg)
                if payload:
                    log.error(f"Payload that caused error: {payload}")
                failed_assistants.append({
                    "name": assistant_name,
                    "old_id": old_id,
                    "graph_id": assistant.get("graph_id", "unknown"),
                    "error": str(e)
                })

        # Increment cache version to invalidate frontend caches
        async with get_db_connection() as conn:
            await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
            await conn.fetchval("SELECT langconnect.increment_cache_version('threads')")

        duration_ms = int((time.time() - start_time) * 1000)

        summary = (
            f"Reverse sync completed: {recreated_count}/{total_assistants} assistants "
            f"successfully recreated in LangGraph"
        )

        if failed_count > 0:
            summary += f", {failed_count} failed"

        log.info(
            f"Reverse sync completed: {recreated_count} successful, {failed_count} failed "
            f"in {duration_ms}ms"
        )

        return {
            "total": total_assistants,
            "recreated": recreated_count,
            "failed": failed_count,
            "failed_assistants": failed_assistants,
            "duration_ms": duration_ms,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to reverse sync assistants: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reverse sync assistants: {str(e)}"
        ) 