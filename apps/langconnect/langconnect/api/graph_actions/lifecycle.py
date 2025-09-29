"""
Graph lifecycle management endpoints: discovery, initialization, and cleanup.
"""

import logging
import time
from typing import Annotated, Dict, List, Set, Any
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import os

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    GraphScanResponse, 
    GraphScanItem, 
    GraphScanMetadata, 
    GraphInitializeRequest,
    GraphInitializeResponse,
    PermissionCreated,
    GraphCleanupRequest,
    GraphCleanupResponse,
    DeletedAssistant,
    CleanupSummary,
    PermissionCleanup,
    AdminInitializePlatformRequest,
    AdminInitializePlatformResponse,
    EnhancementResult,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
 
from langconnect.services.langgraph_sync import LangGraphSyncService, get_sync_service
from langconnect.database.permissions import GraphPermissionsManager, AssistantPermissionsManager

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter()


def generate_human_readable_name(graph_id: str) -> str:
    """Convert graph_id to human-readable default assistant name."""
    # Convert underscore-separated to title case
    # 'supervisor_agent' -> 'Supervisor Agent'
    # 'tools_agent' -> 'Tools Agent' 
    # 'testing_agent_autocreation_v2' -> 'Testing Agent Autocreation V2'
    words = graph_id.replace('_', ' ').split()
    title_words = []
    
    for word in words:
        # Handle version patterns like 'v2', 'v1'
        if word.lower().startswith('v') and len(word) > 1 and word[1:].isdigit():
            title_words.append(word.upper())
        else:
            title_words.append(word.capitalize())
    
    human_name = ' '.join(title_words)
    return f"Default {human_name}"


def is_system_assistant_enhanced(assistant: Dict) -> bool:
    """Check if a system assistant has been enhanced with proper default metadata."""
    metadata = assistant.get("metadata", {})
    
    # Must be system created
    if metadata.get("created_by") != "system":
        return False
    
    # Must have default tag
    if not metadata.get("_x_oap_is_default"):
        return False
    
    # Name should be human-readable (start with "Default")
    name = assistant.get("name", "")
    if not name.startswith("Default "):
        return False
    
    return True


async def cleanup_orphaned_graph(
    graph_id: str,
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """
    Clean up a single orphaned graph and all its associated data.
    
    This function removes:
    - All assistants from LangGraph for this graph
    - Graph permissions from LangConnect database
    - Assistant metadata from LangConnect database  
    - Assistant permissions from LangConnect database
    
    Args:
        graph_id: The graph ID to clean up
        langgraph_service: LangGraph service instance
        actor: The authenticated actor performing the cleanup
        
    Returns:
        Dict with cleanup results and metadata
    """
    try:
        log.info(f"Auto-cleaning orphaned graph: {graph_id}")
        cleanup_results = {
            "graph_id": graph_id,
            "deleted_assistants": [],
            "graph_permissions_removed": 0,
            "assistant_permissions_removed": 0,
            "metadata_records_removed": 0,
            "success": True,
            "error": None
        }
        
        # Step 1: Get and delete ALL assistants for this graph from LangGraph
        try:
            langgraph_assistants_data = await langgraph_service._make_request(
                "POST", 
                "assistants/search", 
                data={
                    "graph_id": graph_id,
                    "limit": 1000,
                    "offset": 0
                }
            )
            langgraph_assistants = langgraph_assistants_data if isinstance(langgraph_assistants_data, list) else langgraph_assistants_data.get("assistants", [])
            
            # Delete each assistant from LangGraph
            for assistant in langgraph_assistants:
                assistant_id = assistant.get("assistant_id")
                if assistant_id:
                    try:
                        await langgraph_service._make_request(
                            "DELETE",
                            f"assistants/{assistant_id}"
                        )
                        cleanup_results["deleted_assistants"].append({
                            "assistant_id": assistant_id,
                            "name": assistant.get("name", f"Assistant {assistant_id}")
                        })
                        log.info(f"Deleted orphaned assistant {assistant_id} from LangGraph")
                    except Exception as e:
                        log.warning(f"Failed to delete assistant {assistant_id} from LangGraph: {e}")
            
            log.info(f"Cleaned up {len(cleanup_results['deleted_assistants'])} assistants from LangGraph for graph {graph_id}")
            
        except Exception as e:
            log.warning(f"Failed to get/delete assistants from LangGraph for graph {graph_id}: {e}")
        
        # Step 2: Clean up database records
        try:
            # Clean up graph permissions
            graph_perms_removed = await GraphPermissionsManager.cleanup_graph_permissions(graph_id, dry_run=False)
            cleanup_results["graph_permissions_removed"] = graph_perms_removed
            
            # Clean up assistant permissions for this graph
            assistant_perms_removed = await GraphPermissionsManager.cleanup_assistant_permissions_for_graph(graph_id, dry_run=False)
            cleanup_results["assistant_permissions_removed"] = assistant_perms_removed
            
            # Clean up assistant metadata for this graph
            metadata_removed = await GraphPermissionsManager.cleanup_assistant_metadata_for_graph(graph_id, dry_run=False)
            cleanup_results["metadata_records_removed"] = metadata_removed
            
            log.info(f"Cleaned up database records for graph {graph_id}: {graph_perms_removed} graph perms, {assistant_perms_removed} assistant perms, {metadata_removed} metadata records")
            
        except Exception as e:
            log.error(f"Failed to clean up database records for graph {graph_id}: {e}")
            cleanup_results["error"] = f"Database cleanup failed: {str(e)}"
        
        log.info(f"Successfully auto-cleaned orphaned graph {graph_id}")
        return cleanup_results
        
    except Exception as e:
        log.error(f"Failed to auto-clean orphaned graph {graph_id}: {e}")
        return {
            "graph_id": graph_id,
            "deleted_assistants": [],
            "graph_permissions_removed": 0,
            "assistant_permissions_removed": 0,
            "metadata_records_removed": 0,
            "success": False,
            "error": str(e)
        }


@router.get("/graphs/scan", response_model=GraphScanResponse)
async def scan_graphs(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> GraphScanResponse:
    """
    Discover and validate graphs from LangGraph with automatic cleanup.
    
    This endpoint scans the LangGraph deployment to find available graphs,
    validates their schemas, and automatically cleans up any orphaned graphs.
    
    - **Read-only discovery**: No manual data modification 
    - **Automatic cleanup**: Invalid graphs are automatically removed
    - **Simplified response**: No enhancement detection or user-specific logic
    - **Validation included**: Schema accessibility testing
    
    **Phase 1 Simplification**: Enhancement detection logic removed and moved to admin endpoint.
    """
    start_time = time.time()
    
    try:
        log.info(f"Starting simplified graph scan with auto-cleanup for {actor.actor_type}:{actor.identity}")
        
        # Step 1: Discover graphs by getting assistants from LangGraph
        assistants_data = await langgraph_service._make_request(
            "POST", 
            "assistants/search", 
            data={
                "limit": 1000,
                "offset": 0,
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        )
        assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
        
        log.info(f"Found {len(assistants)} assistants in LangGraph")
        
        # Step 2: Extract unique graph IDs
        graph_ids: Set[str] = set()
        assistants_by_graph: Dict[str, List[Dict]] = {}
        
        for assistant in assistants:
            graph_id = assistant.get("graph_id")
            if graph_id:
                graph_ids.add(graph_id)
                if graph_id not in assistants_by_graph:
                    assistants_by_graph[graph_id] = []
                assistants_by_graph[graph_id].append(assistant)
        
        log.info(f"Discovered {len(graph_ids)} unique graphs: {list(graph_ids)}")
        
        # Step 3: Validate each graph and identify orphaned ones for cleanup
        valid_graphs: List[GraphScanItem] = []
        invalid_graphs: List[GraphScanItem] = []
        cleanup_performed = []
        
        for graph_id in graph_ids:
            graph_assistants = assistants_by_graph.get(graph_id, [])
            assistants_count = len(graph_assistants)
            
            # Check if there's a default assistant (system created)
            has_default_assistant = any(
                assistant.get("metadata", {}).get("created_by") == "system" 
                for assistant in graph_assistants
            )
            
            # Test schema accessibility
            schema_accessible = False
            error_message = None
            
            try:
                if graph_assistants:
                    first_assistant_id = graph_assistants[0].get("assistant_id")
                    if first_assistant_id:
                        await langgraph_service._make_request(
                            "GET", 
                            f"assistants/{first_assistant_id}/schemas"
                        )
                        schema_accessible = True
                        log.debug(f"Schema accessible for graph {graph_id}")
                    else:
                        error_message = "No assistant ID found"
                else:
                    error_message = "No assistants found for graph"
            except Exception as e:
                error_message = f"Schema endpoint error: {str(e)}"
                log.debug(f"Schema not accessible for graph {graph_id}: {error_message}")
            
            # 🧹 AUTOMATIC CLEANUP: If graph is invalid and has orphaned data, clean it up
            if not schema_accessible and assistants_count > 0:
                log.warning(f"Detected orphaned graph {graph_id} with {assistants_count} assistants - triggering automatic cleanup")
                
                cleanup_result = await cleanup_orphaned_graph(
                    graph_id=graph_id,
                    langgraph_service=langgraph_service,
                    actor=actor
                )
                
                cleanup_performed.append(cleanup_result)
                
                # Skip adding this graph to invalid_graphs since we cleaned it up
                log.info(f"Auto-cleanup completed for orphaned graph {graph_id} - removing from scan results")
                continue
            
            # Create simplified graph item (no enhancement detection)
            graph_item = GraphScanItem(
                graph_id=graph_id,
                schema_accessible=schema_accessible,
                assistants_count=assistants_count,
                has_default_assistant=has_default_assistant,
                needs_initialization=not has_default_assistant,
                error=error_message if not schema_accessible else None,
                cleanup_required=not schema_accessible and assistants_count > 0,
                # Enhancement fields set to None (moved to admin endpoint)
                needs_enhancement=None,
                needs_system_enhancement=None,
                needs_user_inheritance=None,
                needs_dev_admin_sync=None,
                user_permission_level=None
            )
            
            if schema_accessible:
                valid_graphs.append(graph_item)
            else:
                invalid_graphs.append(graph_item)
        
        # Step 4: Create scan metadata with cleanup info
        scan_duration_ms = int((time.time() - start_time) * 1000)
        scan_metadata = GraphScanMetadata(
            langgraph_graphs_found=len(graph_ids),
            valid_graphs=len(valid_graphs),
            invalid_graphs=len(invalid_graphs),
            scan_duration_ms=scan_duration_ms
        )
        
        # Log cleanup summary
        if cleanup_performed:
            total_cleaned = len(cleanup_performed)
            total_assistants_cleaned = sum(len(c["deleted_assistants"]) for c in cleanup_performed)
            total_graph_perms_cleaned = sum(c["graph_permissions_removed"] for c in cleanup_performed)
            total_assistant_perms_cleaned = sum(c["assistant_permissions_removed"] for c in cleanup_performed)
            
            log.info(f"Auto-cleanup summary: {total_cleaned} orphaned graphs cleaned, {total_assistants_cleaned} assistants removed, {total_graph_perms_cleaned} graph permissions removed, {total_assistant_perms_cleaned} assistant permissions removed")
        
        log.info(f"Simplified graph scan completed: {len(valid_graphs)} valid, {len(invalid_graphs)} invalid{f', {len(cleanup_performed)} auto-cleaned' if cleanup_performed else ''} in {scan_duration_ms}ms")
        
        return GraphScanResponse(
            valid_graphs=valid_graphs,
            invalid_graphs=invalid_graphs,
            scan_metadata=scan_metadata
        )
        
    except Exception as e:
        log.error(f"Failed to scan graphs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan graphs: {str(e)}"
        )


async def enhance_system_metadata(
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """
    Scenario 1: System-Wide Graph Setup
    
    Enhance system-created assistants with proper default metadata and human-readable names.
    This handles NEW GRAPHS that have system assistants but no enhanced metadata.
    
    - Updates names to human-readable format ("Default Tools Agent")
    - Adds _x_oap_is_default metadata flag
    - Adds _x_oap_is_primary flag for deployment's defaultGraphId
    - Grants graph permissions to all dev_admins
    - Grants assistant permissions to all dev_admins
    """
    log.info("Starting system metadata enhancement (Scenario 1: Global setup)")
    
    # Get deployment configuration to determine primary assistant
    default_graph_id = os.getenv("NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID")
    
    if not default_graph_id:
        log.warning("No default graph ID found in NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID, using fallback")
        default_graph_id = "tools_agent"
    else:
        log.info(f"Found default graph ID from deployment config: {default_graph_id}")
    
    # Find all system assistants that need metadata enhancement
    assistants_data = await langgraph_service._make_request(
        "POST", 
        "assistants/search", 
        data={
            "limit": 1000,
            "offset": 0,
            "metadata": {"created_by": "system"}
        }
    )
    system_assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
    
    # Filter assistants that need metadata enhancement
    assistants_to_enhance = [
        assistant for assistant in system_assistants
        if not is_system_assistant_enhanced(assistant)
    ]
    
    if not assistants_to_enhance:
        log.info("No assistants need system metadata enhancement")
        return {
            "enhanced_assistants": [],
            "total_enhanced": 0,
            "skipped": len(system_assistants),
            "message": "All system assistants have proper metadata"
        }
    
    log.info(f"Found {len(assistants_to_enhance)} assistants needing system metadata enhancement")
    
    # Get all dev_admins for permission setup
    dev_admins = await GraphPermissionsManager.get_all_dev_admins()
    log.info(f"Found {len(dev_admins)} dev_admin users for permission setup")
    
    enhanced_assistants = []
    successful_enhancements = 0
    failed_enhancements = 0
    errors = []
    
    for assistant in assistants_to_enhance:
        assistant_id = assistant.get("assistant_id")
        graph_id = assistant.get("graph_id")
        
        try:
            log.info(f"Enhancing system metadata for assistant {assistant_id} in graph {graph_id}")
            
            # Generate human-readable name and description
            human_name = generate_human_readable_name(graph_id)
            words = graph_id.replace('_', ' ').split()
            title_words = []
            
            for word in words:
                if word.lower().startswith('v') and len(word) > 1 and word[1:].isdigit():
                    title_words.append(word.upper())
                else:
                    title_words.append(word.capitalize())
            
            human_graph_name = ' '.join(title_words)
            is_primary = graph_id == default_graph_id
            
            # Build enhanced metadata (without description; rely on top-level description)
            current_metadata = assistant.get("metadata", {})
            enhanced_metadata = {
                **current_metadata,
                "_x_oap_is_default": True
            }
            
            if is_primary:
                enhanced_metadata["_x_oap_is_primary"] = True
            
            # Update assistant in LangGraph (set top-level description only)
            update_payload = {
                "name": human_name,
                "description": f"Default assistant for {human_graph_name}",
                "metadata": enhanced_metadata,
                "config": assistant.get("config", {}),
                "graph_id": graph_id
            }
            
            updated_assistant = await langgraph_service._make_request(
                "PATCH",
                f"assistants/{assistant_id}",
                data=update_payload
            )
            
            # Grant graph permissions to all dev_admins
            graph_permissions_created = 0
            for dev_admin in dev_admins:
                has_permission = await GraphPermissionsManager.has_graph_permission(
                    user_id=dev_admin["user_id"],
                    graph_id=graph_id,
                    required_level="access"
                )
                
                if not has_permission:
                    success = await GraphPermissionsManager.grant_graph_permission(
                        graph_id=graph_id,
                        user_id=dev_admin["user_id"],
                        permission_level="admin",
                        granted_by="system:admin_initialisation"
                    )
                    
                    if success:
                        graph_permissions_created += 1
                        log.info(f"Granted graph permission to dev_admin: {dev_admin['email']}")
            
            # Register assistant in permission system
            existing_metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
            if not existing_metadata:
                registration_success = await AssistantPermissionsManager.register_assistant(
                    assistant_id=assistant_id,
                    graph_id=graph_id,
                    owner_id="system",
                    display_name=human_name,
                    description=f"Default assistant for {human_graph_name}"
                )
                
                if registration_success:
                    log.info(f"Registered assistant {assistant_id} in permission system")
            
            # Grant assistant permissions to all dev_admins
            assistant_permissions_created = 0
            for dev_admin in dev_admins:
                existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                    user_id=dev_admin["user_id"],
                    assistant_id=assistant_id
                )
                
                if not existing_permission:
                    # Grant assistant permission to dev_admin
                    # For default assistants, dev_admins get viewer-only access (cannot edit system assistants)
                    success = await AssistantPermissionsManager.grant_assistant_permission(
                        assistant_id=assistant_id,
                        user_id=dev_admin["user_id"],
                        permission_level="viewer",  # Changed from "owner" to "viewer" for default assistants
                        granted_by="system:admin_initialisation"
                    )
                    
                    if success:
                        assistant_permissions_created += 1
                        log.info(f"Granted viewer permission to dev_admin: {dev_admin['email']}")
                    else:
                        log.warning(f"Failed to grant assistant permission to dev_admin: {dev_admin['email']}")
                else:
                    log.info(f"Dev_admin {dev_admin['email']} already has permission for assistant {assistant_id}")
            
            enhanced_assistants.append({
                "assistant_id": assistant_id,
                "graph_id": graph_id,
                "old_name": assistant.get("name", "unknown"),
                "new_name": human_name,
                "is_primary": is_primary,
                "metadata_added": ["_x_oap_is_default"] + (["_x_oap_is_primary"] if is_primary else []),
                "graph_permissions_created": graph_permissions_created,
                "assistant_permissions_created": assistant_permissions_created
            })
            
            successful_enhancements += 1
            log.info(f"Successfully enhanced system metadata for assistant {assistant_id}")
            # Targeted sync so mirrors reflect name/description immediately
            try:
                sync_service = get_sync_service()
                await sync_service.sync_assistant(assistant_id)
            except Exception as sync_err:
                log.warning(f"Post-update mirror sync failed for assistant {assistant_id}: {sync_err}")
            
        except Exception as e:
            failed_enhancements += 1
            error_msg = f"Failed to enhance system metadata for assistant {assistant_id}: {str(e)}"
            log.error(error_msg)
            errors.append(error_msg)
    
    return {
        "enhanced_assistants": enhanced_assistants,
        "total_enhanced": successful_enhancements,
        "failed": failed_enhancements,
        "errors": errors,
        "message": f"Enhanced system metadata for {successful_enhancements} assistants"
    }


async def apply_permission_inheritance(
    user_id: str,
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """
    Scenario 2: User-Specific Permission Inheritance
    
    Grant assistant permissions to a user based on their existing graph permissions.
    This implements the rule: Graph Access → Auto-access to default assistant
    
    - Finds all graphs the user has access to
    - For each graph, finds default assistants
    - Grants assistant permissions if missing
    """
    log.info(f"Starting permission inheritance for user {user_id} (Scenario 2: User-specific)")
    
    # Get user's graph permissions
    user_graph_permissions = await GraphPermissionsManager.get_user_accessible_graphs(user_id)
    log.info(f"User {user_id} has access to {len(user_graph_permissions)} graphs")
    
    if not user_graph_permissions:
        log.info(f"User {user_id} has no graph permissions, skipping inheritance")
        return {
            "inherited_permissions": [],
            "total_inherited": 0,
            "message": "User has no graph permissions"
        }
    
    inherited_permissions = []
    successful_inheritances = 0
    failed_inheritances = 0
    errors = []
    
    for graph_permission in user_graph_permissions:
        graph_id = graph_permission["graph_id"]
        
        try:
            log.info(f"Processing inheritance for graph {graph_id}")
            
            # Find default assistants for this graph
            assistants_data = await langgraph_service._make_request(
                "POST", 
                "assistants/search", 
                data={
                    "graph_id": graph_id,
                    "limit": 100,
                    "offset": 0
                }
            )
            assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
            
            # Filter for enhanced default assistants
            default_assistants = [
                assistant for assistant in assistants
                if is_system_assistant_enhanced(assistant)
            ]
            
            log.info(f"Found {len(default_assistants)} default assistants for graph {graph_id}")
            
            for assistant in default_assistants:
                assistant_id = assistant.get("assistant_id")
                
                # Check if user already has permission for this assistant
                existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                    user_id=user_id,
                    assistant_id=assistant_id
                )
                
                if not existing_permission:
                    # Grant assistant permission to implement inheritance
                    # For default assistants, users get viewer-only access (cannot edit system assistants)
                    success = await AssistantPermissionsManager.grant_assistant_permission(
                        assistant_id=assistant_id,
                        user_id=user_id,
                        permission_level="viewer",  # Changed from "owner" to "viewer" for default assistants
                        granted_by="system:public"
                    )
                    
                    if success:
                        inherited_permissions.append({
                            "assistant_id": assistant_id,
                            "graph_id": graph_id,
                            "assistant_name": assistant.get("name", "Unknown"),
                            "permission_level": "viewer"
                        })
                        successful_inheritances += 1
                        log.info(f"Granted inherited viewer permission to user: {user_id} (graph access → assistant access)")
                    else:
                        log.warning(f"Failed to grant inherited assistant permission to user: {user_id}")
                else:
                    log.info(f"User {user_id} already has permission for assistant {assistant_id}")
                    
        except Exception as e:
            failed_inheritances += 1
            error_msg = f"Failed to process inheritance for graph {graph_id}: {str(e)}"
            log.error(error_msg)
            errors.append(error_msg)
    
    return {
        "inherited_permissions": inherited_permissions,
        "total_inherited": successful_inheritances,
        "failed": failed_inheritances,
        "errors": errors,
        "message": f"Applied inheritance: {successful_inheritances} permissions granted"
    }


async def sync_dev_admin_permissions(
    user_id: str,
    langgraph_service: LangGraphService,
    actor: AuthenticatedActor
) -> Dict[str, Any]:
    """
    Scenario 3: New Dev Admin Catch-Up
    
    Grant graph and assistant permissions to a dev_admin for all existing enhanced graphs.
    This handles new dev_admin users who need access to already-set-up graphs.
    
    - Finds all enhanced graphs
    - Grants graph admin permissions if missing
    - Grants assistant owner permissions if missing
    """
    log.info(f"Starting dev_admin permission sync for user {user_id} (Scenario 3: Role catch-up)")
    
    # Verify user is actually a dev_admin
    user_role = await GraphPermissionsManager.get_user_role(user_id)
    if user_role != "dev_admin":
        log.warning(f"User {user_id} is not a dev_admin, skipping sync")
        return {
            "synced_permissions": [],
            "total_synced": 0,
            "message": "User is not a dev_admin"
        }
    
    # Find all enhanced graphs (graphs with default assistants that have been enhanced)
    assistants_data = await langgraph_service._make_request(
        "POST", 
        "assistants/search", 
        data={
            "limit": 1000,
            "offset": 0,
            "metadata": {"_x_oap_is_default": True}
        }
    )
    enhanced_assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
    
    # Get unique graph IDs from enhanced assistants
    enhanced_graph_ids = set(assistant.get("graph_id") for assistant in enhanced_assistants if assistant.get("graph_id"))
    log.info(f"Found {len(enhanced_graph_ids)} enhanced graphs: {list(enhanced_graph_ids)}")
    
    synced_permissions = []
    successful_syncs = 0
    failed_syncs = 0
    errors = []
    
    for graph_id in enhanced_graph_ids:
        try:
            log.info(f"Syncing dev_admin permissions for graph {graph_id}")
            
            # Check if dev_admin already has graph permission
            has_graph_permission = await GraphPermissionsManager.has_graph_permission(
                user_id=user_id,
                graph_id=graph_id,
                required_level="access"
            )
            
            if not has_graph_permission:
                # Grant graph permission
                success = await GraphPermissionsManager.grant_graph_permission(
                    graph_id=graph_id,
                    user_id=user_id,
                    permission_level="admin",
                    granted_by="system:admin_initialisation"
                )
                
                if success:
                    synced_permissions.append({
                        "type": "graph",
                        "graph_id": graph_id,
                        "permission_level": "admin"
                    })
                    successful_syncs += 1
                    log.info(f"Granted graph admin permission for {graph_id} to dev_admin {user_id}")
            
            # Grant assistant permissions for all enhanced assistants in this graph
            graph_assistants = [a for a in enhanced_assistants if a.get("graph_id") == graph_id]
            
            for assistant in graph_assistants:
                assistant_id = assistant.get("assistant_id")
                
                # First, ensure assistant is registered in metadata table
                existing_metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
                if not existing_metadata:
                    # Register the assistant with system as owner
                    human_name = generate_human_readable_name(graph_id)
                    human_graph_name = human_name.replace(" Assistant", "")
                    
                    registration_success = await AssistantPermissionsManager.register_assistant(
                        assistant_id=assistant_id,
                        graph_id=graph_id,
                        owner_id="system",
                        display_name=human_name,
                        description=f"Default assistant for {human_graph_name}"
                    )
                    
                    if registration_success:
                        synced_permissions.append({
                            "type": "assistant_registration",
                            "assistant_id": assistant_id,
                            "graph_id": graph_id,
                            "action": "registered"
                        })
                        successful_syncs += 1
                        log.info(f"Registered assistant {assistant_id} in metadata table")
                
                # Then grant permission to the dev_admin user
                existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                    user_id=user_id,
                    assistant_id=assistant_id
                )
                
                if not existing_permission:
                    success = await AssistantPermissionsManager.grant_assistant_permission(
                        assistant_id=assistant_id,
                        user_id=user_id,
                        permission_level="owner",
                        granted_by="system:admin_initialisation"
                    )
                    
                    if success:
                        synced_permissions.append({
                            "type": "assistant",
                            "assistant_id": assistant_id,
                            "graph_id": graph_id,
                            "permission_level": "owner"
                        })
                        successful_syncs += 1
                        log.info(f"Granted assistant owner permission for {assistant_id} to dev_admin {user_id}")
                        
        except Exception as e:
            failed_syncs += 1
            error_msg = f"Failed to sync permissions for graph {graph_id}: {str(e)}"
            log.error(error_msg)
            errors.append(error_msg)
    
    return {
        "synced_permissions": synced_permissions,
        "total_synced": successful_syncs,
        "failed": failed_syncs,
        "errors": errors,
        "message": f"Synced {successful_syncs} permissions for dev_admin"
    }


@router.post("/graphs/enhance-system-metadata")
async def enhance_system_metadata_endpoint(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
):
    """
    Scenario 1: System-Wide Graph Setup Endpoint
    
    Enhance system-created assistants with proper default metadata and human-readable names.
    Only for graphs that have system assistants but no enhanced metadata.
    """
    start_time = time.time()
    
    try:
        log.info(f"System metadata enhancement requested by {actor.actor_type}:{actor.identity}")
        
        # Permission check - only dev_admins or service accounts can enhance
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can enhance system metadata"
                )
        
        result = await enhance_system_metadata(langgraph_service, actor)
        
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to enhance system metadata: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enhance system metadata: {str(e)}"
        )


@router.post("/graphs/apply-inheritance/{user_id}")
async def apply_inheritance_endpoint(
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
):
    """
    Scenario 2: User-Specific Permission Inheritance Endpoint
    
    Grant assistant permissions to a user based on their existing graph permissions.
    Implements: Graph Access → Auto-access to default assistant
    """
    start_time = time.time()
    
    try:
        log.info(f"Permission inheritance requested for user {user_id} by {actor.actor_type}:{actor.identity}")
        
        # Permission check - only self, dev_admins, or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin" and actor.identity != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Can only apply inheritance for yourself unless you're a dev_admin"
                )
        
        result = await apply_permission_inheritance(user_id, langgraph_service, actor)
        
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to apply permission inheritance for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply permission inheritance: {str(e)}"
        )


@router.post("/graphs/sync-dev-admin/{user_id}")
async def sync_dev_admin_endpoint(
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
):
    """
    Scenario 3: New Dev Admin Catch-Up Endpoint
    
    Grant graph and assistant permissions to a dev_admin for all existing enhanced graphs.
    For new dev_admin users who need access to already-set-up graphs.
    """
    start_time = time.time()
    
    try:
        log.info(f"Dev admin sync requested for user {user_id} by {actor.actor_type}:{actor.identity}")
        
        # Permission check - only self, dev_admins, or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin" and actor.identity != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Can only sync dev_admin permissions for yourself unless you're a dev_admin"
                )
        
        result = await sync_dev_admin_permissions(user_id, langgraph_service, actor)
        
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to sync dev_admin permissions for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync dev_admin permissions: {str(e)}"
        )


@router.post("/graphs/enhance-defaults")
async def enhance_default_assistants(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
):
    """
    Enhance system-created assistants with proper default metadata and human-readable names.
    
    This endpoint post-processes system-created assistants to make them proper default assistants:
    - Updates names to human-readable format ("Default Tools Agent")
    - Adds _x_oap_is_default metadata flag
    - Adds _x_oap_is_primary flag for deployment's defaultGraphId
    - Registers assistants in permission system
    
    **Authorization:**
    - **Dev Admins**: Can enhance default assistants
    - **Service Accounts**: Can enhance default assistants
    - **Regular Users**: 403 Forbidden
    """
    start_time = time.time()
    
    try:
        log.info(f"Starting default assistant enhancement by {actor.actor_type}:{actor.identity}")
        
        # Step 1: Permission check - only dev_admins or service accounts can enhance
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can enhance default assistants"
                )
        
        # Step 2: Get deployment configuration to determine primary assistant
        default_graph_id = os.getenv("NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID")
        
        if not default_graph_id:
            log.warning("No default graph ID found in NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID, using fallback")
            default_graph_id = "tools_agent"  # Fallback
        else:
            log.info(f"Found default graph ID from deployment config: {default_graph_id}")
        
        # Step 3: Find all system assistants that need enhancement
        assistants_data = await langgraph_service._make_request(
            "POST", 
            "assistants/search", 
            data={
                "limit": 1000,
                "offset": 0,
                "metadata": {"created_by": "system"}
            }
        )
        system_assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
        
        log.info(f"Found {len(system_assistants)} system assistants")
        
        # Get all dev_admins for permission setup (moved earlier)
        dev_admins = await GraphPermissionsManager.get_all_dev_admins()
        log.info(f"Found {len(dev_admins)} dev_admin users for permission setup")
        
        # Step 4: Filter assistants that need enhancement
        assistants_to_enhance = [
            assistant for assistant in system_assistants
            if not is_system_assistant_enhanced(assistant)
        ]
        
        # Also include assistants that are enhanced but may need permission setup
        assistants_needing_permissions = []
        for assistant in system_assistants:
            if is_system_assistant_enhanced(assistant):
                # Check if this assistant has proper permissions
                assistant_id = assistant.get("assistant_id")
                graph_id = assistant.get("graph_id")
                
                # Check if any dev_admin has permissions for this graph/assistant
                needs_permissions = False
                for dev_admin in dev_admins:
                    has_graph_perm = await GraphPermissionsManager.has_graph_permission(
                        user_id=dev_admin["user_id"],
                        graph_id=graph_id,
                        required_level="access"
                    )
                    has_assistant_perm = await AssistantPermissionsManager.get_user_permission_for_assistant(
                        user_id=dev_admin["user_id"],
                        assistant_id=assistant_id
                    )
                    
                    if not has_graph_perm or not has_assistant_perm:
                        needs_permissions = True
                        break
                
                if needs_permissions:
                    assistants_needing_permissions.append(assistant)
        
        # Combine both lists for processing
        all_assistants_to_process = assistants_to_enhance + assistants_needing_permissions
        
        if not all_assistants_to_process:
            log.info("No assistants need enhancement or permission setup")
            return {
                "enhanced_assistants": [],
                "total_enhanced": 0,
                "skipped": len(system_assistants),
                "message": "All system assistants are properly configured"
            }
        
        log.info(f"Found {len(assistants_to_enhance)} assistants needing metadata enhancement and {len(assistants_needing_permissions)} needing permission setup")
        
        # Step 5: Enhance each assistant
        enhanced_assistants = []
        successful_enhancements = 0
        failed_enhancements = 0
        errors = []
        
        for assistant in all_assistants_to_process:
            assistant_id = assistant.get("assistant_id")
            graph_id = assistant.get("graph_id")
            
            try:
                log.info(f"Enhancing assistant {assistant_id} for graph {graph_id}")
                
                # Generate human-readable name
                human_name = generate_human_readable_name(graph_id)
                
                # Generate human-readable description
                # Convert "tools_agent" -> "Tools Agent" (without "Default" prefix)
                words = graph_id.replace('_', ' ').split()
                title_words = []
                
                for word in words:
                    # Handle version patterns like 'v2', 'v1'
                    if word.lower().startswith('v') and len(word) > 1 and word[1:].isdigit():
                        title_words.append(word.upper())
                    else:
                        title_words.append(word.capitalize())
                
                human_graph_name = ' '.join(title_words)
                
                # Determine if this is the primary assistant
                is_primary = graph_id == default_graph_id
                
                # Build enhanced metadata (without description; rely on top-level description)
                current_metadata = assistant.get("metadata", {})
                enhanced_metadata = {
                    **current_metadata,
                    "_x_oap_is_default": True
                }
                
                if is_primary:
                    enhanced_metadata["_x_oap_is_primary"] = True
                
                # Update assistant in LangGraph (set top-level description only)
                update_payload = {
                    "name": human_name,
                    "description": f"Default assistant for {human_graph_name}",
                    "metadata": enhanced_metadata,
                    # Keep existing config and other fields
                    "config": assistant.get("config", {}),
                    "graph_id": graph_id
                }
                
                updated_assistant = await langgraph_service._make_request(
                    "PATCH",
                    f"assistants/{assistant_id}",
                    data=update_payload
                )
                
                # PERMISSION SETUP: Ensure graph-level permissions exist for dev_admins
                graph_permissions_created = 0
                for dev_admin in dev_admins:
                    # Check if dev_admin already has graph permission
                    has_permission = await GraphPermissionsManager.has_graph_permission(
                        user_id=dev_admin["user_id"],
                        graph_id=graph_id,
                        required_level="access"
                    )
                    
                    if not has_permission:
                        # Grant graph permission to dev_admin
                        success = await GraphPermissionsManager.grant_graph_permission(
                            graph_id=graph_id,
                            user_id=dev_admin["user_id"],
                            permission_level="admin",
                            granted_by="system:admin_initialisation"
                        )
                        
                        if success:
                            graph_permissions_created += 1
                            log.info(f"Granted graph permission to dev_admin: {dev_admin['email']}")
                        else:
                            log.warning(f"Failed to grant graph permission to dev_admin: {dev_admin['email']}")
                    else:
                        log.info(f"Dev_admin {dev_admin['email']} already has graph permission for {graph_id}")
                
                # PERMISSION SETUP: Register assistant in permission system
                existing_metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
                assistant_permissions_created = 0
                
                if not existing_metadata:
                    # Register with system as owner (for metadata tracking)
                    registration_success = await AssistantPermissionsManager.register_assistant(
                        assistant_id=assistant_id,
                        graph_id=graph_id,
                        owner_id="system",  # System owns default assistants for metadata
                        display_name=human_name,
                        description=f"Default assistant for {human_graph_name}"
                    )
                    
                    if registration_success:
                        log.info(f"Registered assistant {assistant_id} in permission system")
                    else:
                        log.warning(f"Failed to register assistant {assistant_id} in permission system")
                
                # Grant assistant access to ALL dev_admins (regardless of existing metadata)
                for dev_admin in dev_admins:
                    # Check if dev_admin already has assistant permission
                    existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                        user_id=dev_admin["user_id"],
                        assistant_id=assistant_id
                    )
                    
                    if not existing_permission:
                        # Grant assistant permission to dev_admin
                        # For default assistants, dev_admins get viewer-only access (cannot edit system assistants)
                        success = await AssistantPermissionsManager.grant_assistant_permission(
                            assistant_id=assistant_id,
                            user_id=dev_admin["user_id"],
                            permission_level="viewer",  # Changed from "owner" to "viewer" for default assistants
                            granted_by="system:admin_initialisation"
                        )
                        
                        if success:
                            assistant_permissions_created += 1
                            log.info(f"Granted viewer permission to dev_admin: {dev_admin['email']}")
                        else:
                            log.warning(f"Failed to grant assistant permission to dev_admin: {dev_admin['email']}")
                    else:
                        log.info(f"Dev_admin {dev_admin['email']} already has permission for assistant {assistant_id}")
                
                # PERMISSION INHERITANCE: Grant assistant access to ALL users with graph access
                # This implements the rule: Graph Access → Auto-access to default assistant
                try:
                    graph_users = await GraphPermissionsManager.get_graph_permissions(graph_id)
                    log.info(f"Found {len(graph_users)} users with access to graph {graph_id}")
                    
                    inheritance_permissions_created = 0
                    for graph_user in graph_users:
                        user_id = graph_user["user_id"]
                        user_email = graph_user.get("email", user_id)
                        
                        # Skip if this user is already a dev_admin (already handled above)
                        is_dev_admin = any(dev_admin["user_id"] == user_id for dev_admin in dev_admins)
                        if is_dev_admin:
                            continue
                        
                        # Check if user already has assistant permission
                        existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                            user_id=user_id,
                            assistant_id=assistant_id
                        )
                        
                        if not existing_permission:
                            # Grant assistant permission to implement inheritance
                            # For default assistants, users get viewer-only access (cannot edit system assistants)
                            success = await AssistantPermissionsManager.grant_assistant_permission(
                                assistant_id=assistant_id,
                                user_id=user_id,
                                permission_level="viewer",  # Changed from "owner" to "viewer" for default assistants
                                granted_by="system:public"
                            )
                            
                            if success:
                                inheritance_permissions_created += 1
                                assistant_permissions_created += 1  # Also count in main counter
                                log.info(f"Granted inherited viewer permission to user: {user_email} (graph access → assistant access)")
                            else:
                                log.warning(f"Failed to grant inherited assistant permission to user: {user_email}")
                        else:
                            log.info(f"User {user_email} already has permission for assistant {assistant_id}")
                    
                    if inheritance_permissions_created > 0:
                        log.info(f"Permission inheritance completed: granted {inheritance_permissions_created} assistant permissions based on graph access")
                        
                except Exception as e:
                    log.error(f"Error during permission inheritance for graph {graph_id}: {e}")
                    # Don't fail the entire enhancement if inheritance fails
                
                enhanced_assistants.append({
                    "assistant_id": assistant_id,
                    "graph_id": graph_id,
                    "old_name": assistant.get("name", "unknown"),
                    "new_name": human_name,
                    "is_primary": is_primary,
                    "metadata_added": ["_x_oap_is_default"] + (["_x_oap_is_primary"] if is_primary else []),
                    "graph_permissions_created": graph_permissions_created,
                    "assistant_permissions_created": assistant_permissions_created
                })
                
                successful_enhancements += 1
                log.info(f"Successfully enhanced assistant {assistant_id}: {assistant.get('name')} -> {human_name} (graph perms: {graph_permissions_created}, assistant perms: {assistant_permissions_created})")
                
            except Exception as e:
                failed_enhancements += 1
                error_msg = f"Failed to enhance assistant {assistant_id}: {str(e)}"
                log.error(error_msg)
                errors.append(error_msg)
        
        
        
        log.info(f"Assistant enhancement completed: {successful_enhancements} successful, {failed_enhancements} failed")
        
        # Sync all enhanced assistants to mirror
        if successful_enhancements > 0:
            try:
                sync_service = get_sync_service()
                for enhanced_assistant in enhanced_assistants:
                    await sync_service.sync_assistant(enhanced_assistant["assistant_id"])
                log.info(f"Synced {len(enhanced_assistants)} enhanced assistants to mirror")
            except Exception as sync_error:
                log.warning(f"Failed to sync enhanced assistants to mirror: {sync_error}")
                # Don't fail the enhancement if sync fails
        
        return {
            "enhanced_assistants": enhanced_assistants,
            "total_enhanced": successful_enhancements,
            "failed": failed_enhancements,
            "skipped": len(system_assistants) - len(all_assistants_to_process),
            "errors": errors,
            "message": f"Enhanced {successful_enhancements} assistants successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to enhance default assistants: {str(e)}")
        
        
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enhance default assistants: {str(e)}"
        )


@router.post("/graphs/{graph_id}/initialize", response_model=GraphInitializeResponse)
async def initialize_graph(
    graph_id: str,
    request: GraphInitializeRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> GraphInitializeResponse:
    """
    Initialize a new graph with default assistant and permissions.
    
    This endpoint performs explicit graph initialization:
    - Verifies graph exists in LangGraph deployment
    - Creates default assistant if needed
    - Grants permissions to dev_admin users
    - Logs initialization activity
    
    **Authorization:**
    - **Dev Admins**: Can initialize any graph
    - **Service Accounts**: Can initialize any graph
    - **Regular Users**: 403 Forbidden
    """
    start_time = time.time()
    
    try:
        log.info(f"Starting graph initialization for {graph_id} by {actor.actor_type}:{actor.identity}")
        
        # Step 1: Permission check - only dev_admins or service accounts can initialize
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can initialize graphs"
                )
        
        # Step 2: Verify graph exists in LangGraph by trying to find its assistants
        assistants_data = await langgraph_service._make_request(
            "POST", 
            "assistants/search", 
            data={
                "graph_id": graph_id,
                "limit": 10,
                "offset": 0
            }
        )
        assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
        
        if not assistants:
            raise HTTPException(
                status_code=404,
                detail=f"Graph '{graph_id}' not found in LangGraph deployment"
            )
        
        log.info(f"Found {len(assistants)} assistants for graph {graph_id}")
        
        # Step 3: Find or create default assistant
        default_assistant = None
        for assistant in assistants:
            if assistant.get("metadata", {}).get("created_by") == "system":
                default_assistant = assistant
                break
        
        if not default_assistant:
            # Create default assistant name
            assistant_name = request.assistant_name or f"Default {graph_id.replace('_', ' ').title()}"
            # Build human-readable graph name for description
            words = graph_id.replace('_', ' ').split()
            title_words = []
            for word in words:
                if word.lower().startswith('v') and len(word) > 1 and word[1:].isdigit():
                    title_words.append(word.upper())
                else:
                    title_words.append(word.capitalize())
            human_graph_name = ' '.join(title_words)
            
            # Create default assistant in LangGraph
            # Note: This is a simplified version - in reality, you'd need the proper config
            default_assistant_data = await langgraph_service._make_request(
                "POST",
                "assistants",
                data={
                    "graph_id": graph_id,
                    "name": assistant_name,
                    "description": f"Default assistant for {human_graph_name}",
                    "config": {"configurable": {}},
                    "metadata": {"created_by": "system", "_x_oap_is_default": True}
                }
            )
            default_assistant = default_assistant_data
            log.info(f"Created new default assistant: {assistant_name}")
        else:
            assistant_name = default_assistant.get("name", f"Default {graph_id.replace('_', ' ').title()}")
            log.info(f"Using existing default assistant: {assistant_name}")
        
        assistant_id = default_assistant.get("assistant_id")
        if not assistant_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to get assistant ID from LangGraph"
            )
        
        # Step 4: Grant permissions to dev_admins if requested
        permissions_created = []
        
        if request.grant_dev_admin_access:
            dev_admins = await GraphPermissionsManager.get_all_dev_admins()
            
            for dev_admin in dev_admins:
                # Grant graph permission
                success = await GraphPermissionsManager.grant_graph_permission(
                    graph_id=graph_id,
                    user_id=dev_admin["user_id"],
                    permission_level="admin",
                    granted_by="system:admin_initialisation"
                )
                
                if success:
                    # Register assistant permission 
                    await AssistantPermissionsManager.register_assistant(
                        assistant_id=assistant_id,
                        graph_id=graph_id,
                        owner_id=dev_admin["user_id"],
                        display_name=assistant_name,
                        description=f"Default assistant for {graph_id}"
                    )
                    
                    permissions_created.append(PermissionCreated(
                        user_role="dev_admin",
                        graph_permission="admin", 
                        assistant_permission="owner"
                    ))
                    
                    log.info(f"Granted permissions to dev_admin: {dev_admin['email']}")
        
        
        
        log.info(f"Graph {graph_id} initialized successfully with {len(permissions_created)} permissions granted")
        
        return GraphInitializeResponse(
            graph_id=graph_id,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            permissions_created=permissions_created,
            created_at=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        log.error(f"Failed to initialize graph {graph_id}: {str(e)}")
        
        
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize graph: {str(e)}"
        )


@router.delete("/graphs/cleanup", response_model=GraphCleanupResponse)
async def cleanup_graphs(
    request: GraphCleanupRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> GraphCleanupResponse:
    """
    Clean up orphaned graphs and their associated data.
    
    This endpoint removes invalid graphs and their assistants from both
    LangGraph and the permission system. It includes safety features:
    - Dry-run mode for previewing changes
    - Confirmation requirement for actual deletion
    - Targeted or automatic cleanup
    
    **Authorization:**
    - **Dev Admins**: Can perform cleanup operations
    - **Service Accounts**: Can perform cleanup operations
    - **Regular Users**: 403 Forbidden
    
    **Safety Features:**
    - **Dry Run**: Preview operations without making changes
    - **Confirmation**: Requires explicit confirmation for deletion
    - **Targeted**: Can clean specific graphs or all invalid ones
    """
    start_time = time.time()
    
    try:
        log.info(f"Starting graph cleanup by {actor.actor_type}:{actor.identity} (dry_run={request.dry_run})")
        
        # Step 1: Permission check - only dev_admins or service accounts can cleanup
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can perform cleanup operations"
                )
        
        # Step 2: Safety check - require confirmation for actual deletion
        if not request.dry_run and not request.confirm_deletion:
            raise HTTPException(
                status_code=400,
                detail="confirm_deletion must be true for actual deletion operations"
            )
        
        # Step 3: Determine which graphs to clean up
        graphs_to_cleanup = []
        warnings = []
        
        if request.target_graphs:
            # Use specific graphs provided
            graphs_to_cleanup = request.target_graphs
            log.info(f"Targeting specific graphs for cleanup: {graphs_to_cleanup}")
        else:
            # Scan for invalid graphs automatically
            log.info("Scanning for invalid graphs to cleanup")
            
            # Get current scan results to find invalid graphs
            assistants_data = await langgraph_service._make_request(
                "POST", 
                "assistants/search", 
                data={"limit": 1000, "offset": 0}
            )
            assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
            
            # Extract unique graph IDs
            graph_ids = set()
            for assistant in assistants:
                graph_id = assistant.get("graph_id")
                if graph_id:
                    graph_ids.add(graph_id)
            
            # Test each graph for validity
            for graph_id in graph_ids:
                graph_assistants = [a for a in assistants if a.get("graph_id") == graph_id]
                
                # Test schema accessibility
                try:
                    if graph_assistants:
                        first_assistant_id = graph_assistants[0].get("assistant_id")
                        if first_assistant_id:
                            await langgraph_service._make_request(
                                "GET", 
                                f"assistants/{first_assistant_id}/schemas"
                            )
                except Exception:
                    # Schema not accessible - mark for cleanup
                    graphs_to_cleanup.append(graph_id)
                    log.info(f"Found invalid graph for cleanup: {graph_id}")
        
        if not graphs_to_cleanup:
            log.info("No graphs found for cleanup")
            return GraphCleanupResponse(
                deleted_graphs=[],
                deleted_assistants=[],
                permissions_cleaned=PermissionCleanup(
                    graph_permissions_removed=0,
                    assistant_permissions_removed=0
                ),
                cleanup_summary=CleanupSummary(
                    total_operations=0,
                    successful=0,
                    failed=0
                ),
                dry_run=request.dry_run,
                warnings=["No graphs found that require cleanup"]
            )
        
        # Step 4: Perform cleanup operations
        deleted_graphs = []
        deleted_assistants = []
        total_graph_perms_removed = 0
        total_assistant_perms_removed = 0
        successful_operations = 0
        failed_operations = 0
        
        for graph_id in graphs_to_cleanup:
            try:
                log.info(f"Cleaning up graph: {graph_id} (dry_run={request.dry_run})")
                
                # Get assistants from our permission database (for permission cleanup)
                orphaned_assistants = await GraphPermissionsManager.get_orphaned_assistants_for_graph(graph_id)
                
                # Get ALL assistants for this graph from LangGraph (including unregistered ones)
                try:
                    langgraph_assistants_data = await langgraph_service._make_request(
                        "POST", 
                        "assistants/search", 
                        data={
                            "graph_id": graph_id,
                            "limit": 1000,
                            "offset": 0
                        }
                    )
                    langgraph_assistants = langgraph_assistants_data if isinstance(langgraph_assistants_data, list) else langgraph_assistants_data.get("assistants", [])
                    log.info(f"Found {len(langgraph_assistants)} assistants in LangGraph for {graph_id}")
                except Exception as e:
                    log.warning(f"Failed to get assistants from LangGraph for {graph_id}: {e}")
                    langgraph_assistants = []

                if not request.dry_run:
                    # Delete ALL assistants from LangGraph (both registered and unregistered)
                    for assistant in langgraph_assistants:
                        assistant_id = assistant.get("assistant_id")
                        if assistant_id:
                            try:
                                await langgraph_service._make_request(
                                    "DELETE",
                                    f"assistants/{assistant_id}"
                                )
                                log.info(f"Deleted assistant {assistant_id} from LangGraph")
                            except Exception as e:
                                log.warning(f"Failed to delete assistant {assistant_id} from LangGraph: {e}")
                                warnings.append(f"Could not delete assistant {assistant_id} from LangGraph: {e}")

                # Clean up permissions (dry-run aware)
                graph_perms_removed = await GraphPermissionsManager.cleanup_graph_permissions(graph_id, request.dry_run)
                assistant_perms_removed = await GraphPermissionsManager.cleanup_assistant_permissions_for_graph(graph_id, request.dry_run)
                metadata_removed = await GraphPermissionsManager.cleanup_assistant_metadata_for_graph(graph_id, request.dry_run)

                # Track results
                total_graph_perms_removed += graph_perms_removed
                total_assistant_perms_removed += assistant_perms_removed

                deleted_graphs.append(graph_id)

                # Add ALL assistants to response (both from permission DB and LangGraph)
                assistant_ids_added = set()
                
                # Add assistants from permission database
                for assistant_info in orphaned_assistants:
                    assistant_id = assistant_info['assistant_id']
                    if assistant_id not in assistant_ids_added:
                        deleted_assistants.append(DeletedAssistant(
                            assistant_id=assistant_id,
                            graph_id=graph_id,
                            name=assistant_info['display_name'] or f"Assistant {assistant_id}"
                        ))
                        assistant_ids_added.add(assistant_id)
                
                # Add assistants from LangGraph that weren't in permission database
                for assistant in langgraph_assistants:
                    assistant_id = assistant.get("assistant_id")
                    if assistant_id and assistant_id not in assistant_ids_added:
                        deleted_assistants.append(DeletedAssistant(
                            assistant_id=assistant_id,
                            graph_id=graph_id,
                            name=assistant.get("name", f"Assistant {assistant_id}")
                        ))
                        assistant_ids_added.add(assistant_id)

                successful_operations += 1
                log.info(f"Successfully cleaned up graph {graph_id}: {len(langgraph_assistants)} LangGraph assistants, {len(orphaned_assistants)} tracked assistants, {graph_perms_removed} graph perms, {assistant_perms_removed} assistant perms")
                
            except Exception as e:
                failed_operations += 1
                error_msg = f"Failed to cleanup graph {graph_id}: {str(e)}"
                log.error(error_msg)
                warnings.append(error_msg)
        
        # Step 5: Create cleanup summary
        total_operations = len(graphs_to_cleanup)
        cleanup_summary = CleanupSummary(
            total_operations=total_operations,
            successful=successful_operations,
            failed=failed_operations
        )
        
        permissions_cleaned = PermissionCleanup(
            graph_permissions_removed=total_graph_perms_removed,
            assistant_permissions_removed=total_assistant_perms_removed
        )
        
        
        
        action_word = "would be" if request.dry_run else "were"
        log.info(f"Graph cleanup completed: {len(deleted_graphs)} graphs {action_word} cleaned, {len(deleted_assistants)} assistants {action_word} deleted")
        
        return GraphCleanupResponse(
            deleted_graphs=deleted_graphs,
            deleted_assistants=deleted_assistants,
            permissions_cleaned=permissions_cleaned,
            cleanup_summary=cleanup_summary,
            dry_run=request.dry_run,
            warnings=warnings
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        log.error(f"Failed to perform graph cleanup: {str(e)}")
        
        
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to perform graph cleanup: {str(e)}"
        )


# ==================== ADMIN PLATFORM INITIALIZATION ====================
# NOTE: Admin platform initialization has been moved to admin_actions.py
# The endpoint is now at /agents/admin/initialize-platform 