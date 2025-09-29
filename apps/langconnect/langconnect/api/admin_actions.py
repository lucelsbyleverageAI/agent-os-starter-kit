"""
Admin-level operations for platform initialization and maintenance.

This module contains admin-only endpoints that are separate from regular user workflows.
These operations are typically performed by dev_admins to set up and maintain the platform.
"""

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
    Admin endpoint to initialize the platform by performing all enhancement operations.
    
    This consolidated admin endpoint performs all three enhancement scenarios:
    - Scenario 1: System-Wide Graph Setup (enhance system metadata)
    - Scenario 2: User-Specific Permission Inheritance (apply inheritance)
    - Scenario 3: New Dev Admin Catch-Up (sync dev admin permissions)
    
    **Phase 1 Consolidation**: All enhancement logic moved from discovery to this explicit admin action.
    
    **Authorization:**
    - **Dev Admins**: Can initialize platform
    - **Service Accounts**: Can initialize platform
    - **Regular Users**: 403 Forbidden
    
    **Options:**
    - **Dry Run**: Preview operations without making changes
    - **Target User**: Focus inheritance/sync on specific user (optional)
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
        
        # Step 2: Scenario 1 - System-Wide Graph Setup
        log.info("Performing Scenario 1: System-Wide Graph Setup")
        try:
            if not request.dry_run:
                system_result = await enhance_system_metadata(langgraph_service, actor)
            else:
                # For dry run, simulate the operation
                system_result = {
                    "enhanced_assistants": [],
                    "total_enhanced": 0,
                    "failed": 0,
                    "errors": [],
                    "message": "DRY RUN: Would enhance system assistants with proper metadata"
                }
            
            operations_performed.append(EnhancementResult(
                operation="system_metadata_enhancement",
                success=system_result["failed"] == 0,
                total_enhanced=system_result["total_enhanced"],
                failed=system_result["failed"],
                message=system_result["message"],
                errors=system_result.get("errors", [])
            ))
            
            if system_result["failed"] == 0:
                successful_operations += 1
            else:
                failed_operations += 1
            
            log.info(f"Scenario 1 completed: {system_result['total_enhanced']} enhanced, {system_result['failed']} failed")
            
        except Exception as e:
            failed_operations += 1
            error_msg = f"Scenario 1 failed: {str(e)}"
            log.error(error_msg)
            warnings.append(error_msg)
            operations_performed.append(EnhancementResult(
                operation="system_metadata_enhancement",
                success=False,
                total_enhanced=0,
                failed=1,
                message="Failed to enhance system metadata",
                errors=[str(e)]
            ))
        
        # Step 3: Scenario 2 - User-Specific Permission Inheritance
        log.info("Performing Scenario 2: User-Specific Permission Inheritance")
        try:
                         # Determine target users for inheritance
            if request.target_user_id:
                target_users = [request.target_user_id]
            else:
                # Apply to all users who might need inheritance (not dev_admins)
                # Get unique users from graph_permissions table who are not dev_admins
                from langconnect.database.connection import get_db_connection
                async with get_db_connection() as conn:
                    results = await conn.fetch(
                        """
                        SELECT DISTINCT gp.user_id, ur.role
                        FROM langconnect.graph_permissions gp
                        JOIN langconnect.user_roles ur ON gp.user_id = ur.user_id
                        WHERE ur.role != 'dev_admin'
                        """
                    )
                    target_users = [row["user_id"] for row in results]
            
            total_inherited = 0
            total_inheritance_failed = 0
            inheritance_errors = []
            
            for user_id in target_users:
                try:
                    if not request.dry_run:
                        inheritance_result = await apply_permission_inheritance(user_id, langgraph_service, actor)
                    else:
                        # For dry run, simulate the operation
                        inheritance_result = {
                            "inherited_permissions": [],
                            "total_inherited": 0,
                            "failed": 0,
                            "errors": [],
                            "message": f"DRY RUN: Would apply inheritance for user {user_id}"
                        }
                    
                    total_inherited += inheritance_result["total_inherited"]
                    total_inheritance_failed += inheritance_result["failed"]
                    inheritance_errors.extend(inheritance_result.get("errors", []))
                    
                except Exception as e:
                    total_inheritance_failed += 1
                    inheritance_errors.append(f"User {user_id}: {str(e)}")
                    log.error(f"Inheritance failed for user {user_id}: {e}")
            
            operations_performed.append(EnhancementResult(
                operation="user_permission_inheritance",
                success=total_inheritance_failed == 0,
                total_enhanced=total_inherited,
                failed=total_inheritance_failed,
                message=f"Applied permission inheritance to {len(target_users)} users",
                errors=inheritance_errors
            ))
            
            if total_inheritance_failed == 0:
                successful_operations += 1
            else:
                failed_operations += 1
            
            log.info(f"Scenario 2 completed: {total_inherited} permissions inherited, {total_inheritance_failed} failed")
            
        except Exception as e:
            failed_operations += 1
            error_msg = f"Scenario 2 failed: {str(e)}"
            log.error(error_msg)
            warnings.append(error_msg)
            operations_performed.append(EnhancementResult(
                operation="user_permission_inheritance",
                success=False,
                total_enhanced=0,
                failed=1,
                message="Failed to apply permission inheritance",
                errors=[str(e)]
            ))
        
        # Step 4: Scenario 3 - New Dev Admin Catch-Up
        log.info("Performing Scenario 3: New Dev Admin Catch-Up")
        try:
            # Get all dev_admins for sync
            dev_admins = await GraphPermissionsManager.get_all_dev_admins()
            target_dev_admins = [request.target_user_id] if request.target_user_id else [admin["user_id"] for admin in dev_admins]
            
            total_synced = 0
            total_sync_failed = 0
            sync_errors = []
            
            for admin_id in target_dev_admins:
                try:
                    if not request.dry_run:
                        sync_result = await sync_dev_admin_permissions(admin_id, langgraph_service, actor)
                    else:
                        # For dry run, simulate the operation
                        sync_result = {
                            "synced_permissions": [],
                            "total_synced": 0,
                            "failed": 0,
                            "errors": [],
                            "message": f"DRY RUN: Would sync permissions for dev_admin {admin_id}"
                        }
                    
                    total_synced += sync_result["total_synced"]
                    total_sync_failed += sync_result["failed"]
                    sync_errors.extend(sync_result.get("errors", []))
                    
                except Exception as e:
                    total_sync_failed += 1
                    sync_errors.append(f"Dev admin {admin_id}: {str(e)}")
                    log.error(f"Sync failed for dev_admin {admin_id}: {e}")
            
            operations_performed.append(EnhancementResult(
                operation="dev_admin_permission_sync",
                success=total_sync_failed == 0,
                total_enhanced=total_synced,
                failed=total_sync_failed,
                message=f"Synced permissions for {len(target_dev_admins)} dev_admins",
                errors=sync_errors
            ))
            
            if total_sync_failed == 0:
                successful_operations += 1
            else:
                failed_operations += 1
            
            log.info(f"Scenario 3 completed: {total_synced} permissions synced, {total_sync_failed} failed")
            
        except Exception as e:
            failed_operations += 1
            error_msg = f"Scenario 3 failed: {str(e)}"
            log.error(error_msg)
            warnings.append(error_msg)
            operations_performed.append(EnhancementResult(
                operation="dev_admin_permission_sync",
                success=False,
                total_enhanced=0,
                failed=1,
                message="Failed to sync dev admin permissions",
                errors=[str(e)]
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