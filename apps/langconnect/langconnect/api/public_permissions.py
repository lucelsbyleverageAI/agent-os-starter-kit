"""
API endpoints for managing and materializing public (default-access) permissions.
"""

import logging
from typing import Annotated, Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.database.user_roles import UserRoleManager
from langconnect.database.graph_permissions import GraphPermissionManager
from langconnect.database.permissions import AssistantPermissionsManager
from langconnect.database.collections import CollectionsManager
from langconnect.database.connection import get_db_connection
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/public-permissions",
    tags=["Public Permissions"],
)

class PublicPermissionItem(BaseModel):
    id: int
    permission_level: str
    created_at: str
    revoked_at: Optional[str] = None
    revoke_mode: Optional[str] = None
    notes: Optional[str] = None
    created_by_email: Optional[str] = None
    created_by_display_name: Optional[str] = None

class PublicGraphPermissionItem(PublicPermissionItem):
    graph_id: str
    created_by: str

class PublicAssistantPermissionItem(PublicPermissionItem):
    assistant_id: str
    created_by: str

class PublicCollectionPermissionItem(PublicPermissionItem):
    collection_id: str
    created_by: str

class RevokeRequest(BaseModel):
    revoke_mode: str

class CreatePublicGraphRequest(BaseModel):
    graph_id: str
    permission_level: str
    notes: Optional[str] = None

class CreatePublicAssistantRequest(BaseModel):
    assistant_id: str
    permission_level: str
    notes: Optional[str] = None

class CreatePublicCollectionRequest(BaseModel):
    collection_id: str
    permission_level: str
    notes: Optional[str] = None

@router.get("/graphs", response_model=List[PublicGraphPermissionItem])
async def list_public_graph_permissions(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """List all public graph permissions."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        permissions = await GraphPermissionManager.get_all_public_graph_permissions()
        response = []
        for p in permissions:
            response.append(PublicGraphPermissionItem(
                id=p["id"],
                graph_id=p["graph_id"],
                permission_level=p["permission_level"],
                created_at=p["created_at"].isoformat() if p["created_at"] else None,
                revoked_at=p["revoked_at"].isoformat() if p["revoked_at"] else None,
                revoke_mode=p.get("revoke_mode"),
                notes=p["notes"],
                created_by=p.get("created_by_display_name") or "Unknown"
            ))
        return response

    except Exception as e:
        log.error(f"Error listing public graph permissions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/graphs", response_model=Dict[str, Any])
async def create_public_graph_permission(
    request: CreatePublicGraphRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
):
    """Create a new public graph permission and grant it to all existing users.

    Note: This only grants graph-level permissions. Assistant permissions must be
    granted separately if you want users to access existing assistants created from this graph.
    """
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    # Validate permission level
    if request.permission_level not in ["access", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid permission level. Must be 'access' or 'admin'.")

    try:
        async with get_db_connection() as connection:
            # Use a transaction to ensure consistency
            async with connection.transaction():
                # Check if public permission already exists for this graph
                existing = await connection.fetchrow(
                    "SELECT id FROM langconnect.public_graph_permissions WHERE graph_id = $1 AND revoked_at IS NULL",
                    request.graph_id
                )
                
                if existing:
                    raise HTTPException(status_code=409, detail="Public permission already exists for this graph")

                # Create the public graph permission
                result = await connection.fetchrow(
                    """
                    INSERT INTO langconnect.public_graph_permissions 
                    (graph_id, permission_level, created_by, notes)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, created_at
                    """,
                    request.graph_id, request.permission_level, actor.identity, request.notes
                )

                # Immediately grant this graph permission to all existing users
                granted_result = await connection.execute(
                    """
                    INSERT INTO langconnect.graph_permissions (user_id, graph_id, permission_level, granted_by)
                    SELECT ur.user_id, $1, $2, 'system:public'
                    FROM langconnect.user_roles ur
                    ON CONFLICT (user_id, graph_id) DO NOTHING
                    """,
                    request.graph_id, request.permission_level
                )
                
                # Extract number of users granted graph permission
                users_granted = 0
                if hasattr(granted_result, 'split'):
                    users_granted = int(granted_result.split()[-1]) if granted_result.split()[-1].isdigit() else 0

                log.info(f"User '{actor.identity}' created public permission for graph '{request.graph_id}' with level '{request.permission_level}' and granted to {users_granted} existing users")

                return {
                    "id": result["id"],
                    "graph_id": request.graph_id,
                    "permission_level": request.permission_level,
                    "created_at": result["created_at"].isoformat(),
                    "users_granted": users_granted,
                    "message": f"Public graph permission created successfully and granted to {users_granted} existing users"
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating public graph permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/assistants", response_model=List[PublicAssistantPermissionItem])
async def list_public_assistant_permissions(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """List all public assistant permissions."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        # Get all public assistant permissions (no more implied logic needed)
        direct_permissions = await AssistantPermissionsManager.get_all_public_assistant_permissions()
        
        result = []
        
        # Add all direct permissions (no implied permissions needed since we create real ones)
        for perm in direct_permissions:
            result.append(PublicAssistantPermissionItem(
                id=perm["id"],
                assistant_id=perm["assistant_id"],
                permission_level=perm["permission_level"],
                created_at=perm["created_at"].isoformat() if perm["created_at"] else None,
                revoked_at=perm["revoked_at"].isoformat() if perm["revoked_at"] else None,
                revoke_mode=perm.get("revoke_mode"),
                notes=perm["notes"],
                created_by=perm.get("created_by_display_name") or "Unknown"
            ))
        
        return result

    except Exception as e:
        log.error(f"Error fetching public assistant permissions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/assistants", response_model=Dict[str, Any])
async def create_public_assistant_permission(
    request: CreatePublicAssistantRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Create a new public assistant permission."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    # Validate permission level
    if request.permission_level not in ["viewer", "editor"]:
        raise HTTPException(status_code=400, detail="Invalid permission level. Must be 'viewer' or 'editor'.")

    try:
        async with get_db_connection() as connection:
            # Use a transaction to ensure consistency
            async with connection.transaction():
                # Check if public permission already exists for this assistant
                existing = await connection.fetchrow(
                    "SELECT id FROM langconnect.public_assistant_permissions WHERE assistant_id = $1 AND revoked_at IS NULL",
                    request.assistant_id
                )
                
                if existing:
                    raise HTTPException(status_code=409, detail="Public permission already exists for this assistant")

                # Create the public permission
                result = await connection.fetchrow(
                    """
                    INSERT INTO langconnect.public_assistant_permissions 
                    (assistant_id, permission_level, created_by, notes)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, created_at
                    """,
                    request.assistant_id, request.permission_level, actor.identity, request.notes
                )

                # Immediately grant this permission to all existing users
                granted_result = await connection.execute(
                    """
                    INSERT INTO langconnect.assistant_permissions (user_id, assistant_id, permission_level, granted_by)
                    SELECT ur.user_id, $1, $2, 'system:public'
                    FROM langconnect.user_roles ur
                    ON CONFLICT (user_id, assistant_id) DO NOTHING
                    """,
                    request.assistant_id, request.permission_level
                )
                
                # Extract number of users granted permission
                users_granted = 0
                if hasattr(granted_result, 'split'):
                    users_granted = int(granted_result.split()[-1]) if granted_result.split()[-1].isdigit() else 0

                log.info(f"User '{actor.identity}' created public permission for assistant '{request.assistant_id}' with level '{request.permission_level}' and granted to {users_granted} existing users.")
                
                return {
                    "id": result["id"],
                    "assistant_id": request.assistant_id,
                    "permission_level": request.permission_level,
                    "created_at": result["created_at"].isoformat(),
                    "users_granted": users_granted,
                    "message": f"Public assistant permission created successfully and granted to {users_granted} existing users"
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating public assistant permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.delete("/graphs/{graph_id}")
async def revoke_public_graph_permission(
    graph_id: str,
    request: RevokeRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Revoke a public permission for a graph."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        async with get_db_connection() as connection:
            # First check if there's an active permission
            active_permission = await connection.fetchrow(
                "SELECT id FROM langconnect.public_graph_permissions WHERE graph_id = $1 AND revoked_at IS NULL",
                graph_id
            )
            
            # If there's an active permission, revoke it normally
            if active_permission:
                result = await GraphPermissionManager.revoke_public_graph_permission(graph_id, request.revoke_mode)

                return {
                    "message": "Public graph permission revoked successfully",
                    "result": result
                }
            
            # If no active permission, check for a revoked one that we might want to change mode
            revoked_permission = await connection.fetchrow(
                "SELECT id, revoke_mode FROM langconnect.public_graph_permissions WHERE graph_id = $1 AND revoked_at IS NOT NULL",
                graph_id
            )
            
            if not revoked_permission:
                raise HTTPException(status_code=404, detail=f"No public permission found for graph_id: {graph_id}")
            
            # If we're trying to revoke_all on a future_only revoked permission, update it
            if request.revoke_mode == 'revoke_all' and revoked_permission['revoke_mode'] == 'future_only':
                # Update the revoke mode and remove existing user permissions
                await connection.execute(
                    "UPDATE langconnect.public_graph_permissions SET revoke_mode = 'revoke_all' WHERE graph_id = $1",
                    graph_id
                )

                # Remove existing user permissions that were granted by the public permission
                delete_result = await connection.execute(
                    "DELETE FROM langconnect.graph_permissions WHERE graph_id = $1 AND granted_by = 'system:public'",
                    graph_id
                )

                revoked_count = 0
                if hasattr(delete_result, 'split'):
                    revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0

                return {
                    "message": "Public graph permission updated to revoke all users",
                    "result": {
                        "graph_id": graph_id,
                        "status": "revoked",
                        "mode": "revoke_all",
                        "revoked_user_count": revoked_count
                    }
                }
            else:
                raise HTTPException(status_code=400, detail=f"Permission already revoked with mode: {revoked_permission['revoke_mode']}")

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error revoking public graph permission for {graph_id} by {actor.identity}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/assistants/{assistant_id}")
async def revoke_public_assistant_permission(
    assistant_id: str,
    request: RevokeRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Revoke a public permission for an assistant."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        async with get_db_connection() as connection:
            # First check if there's an active permission
            active_permission = await connection.fetchrow(
                "SELECT id FROM langconnect.public_assistant_permissions WHERE assistant_id = $1 AND revoked_at IS NULL",
                assistant_id
            )
            
            # If there's an active permission, revoke it normally
            if active_permission:
                result = await AssistantPermissionsManager.revoke_public_assistant_permission(assistant_id, request.revoke_mode)
                return {"message": "Public assistant permission revoked successfully", "result": result}
            
            # If no active permission, check for a revoked one that we might want to change mode
            revoked_permission = await connection.fetchrow(
                "SELECT id, revoke_mode FROM langconnect.public_assistant_permissions WHERE assistant_id = $1 AND revoked_at IS NOT NULL",
                assistant_id
            )
            
            if not revoked_permission:
                raise HTTPException(status_code=404, detail=f"No public permission found for assistant_id: {assistant_id}")
            
            # If we're trying to revoke_all on a future_only revoked permission, update it
            if request.revoke_mode == 'revoke_all' and revoked_permission['revoke_mode'] == 'future_only':
                # Update the revoke mode and remove existing user permissions
                await connection.execute(
                    "UPDATE langconnect.public_assistant_permissions SET revoke_mode = 'revoke_all' WHERE assistant_id = $1",
                    assistant_id
                )
                
                # Remove existing user permissions that were granted by the public permission
                delete_result = await connection.execute(
                    "DELETE FROM langconnect.assistant_permissions WHERE assistant_id = $1 AND granted_by = 'system:public'",
                    assistant_id
                )
                
                revoked_count = 0
                if hasattr(delete_result, 'split'):
                    revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0
                
                return {
                    "message": "Public assistant permission updated to revoke all users",
                    "result": {
                        "assistant_id": assistant_id,
                        "status": "revoked",
                        "mode": "revoke_all",
                        "revoked_user_count": revoked_count
                    }
                }
            else:
                raise HTTPException(status_code=400, detail=f"Permission already revoked with mode: {revoked_permission['revoke_mode']}")

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error revoking public assistant permission for {assistant_id} by {actor.identity}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/graphs/{graph_id}/re-invoke")
async def re_invoke_public_graph_permission(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Re-invoke a previously revoked public graph permission."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        # Re-invoke by setting revoked_at back to NULL
        async with get_db_connection() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE langconnect.public_graph_permissions
                    SET revoked_at = NULL, revoke_mode = NULL
                    WHERE graph_id = $1 AND revoked_at IS NOT NULL
                    """,
                    graph_id
                )
                
                if "UPDATE 0" in result:
                    raise HTTPException(status_code=404, detail="No revoked permission found for this graph")

                return {
                    "message": "Public graph permission re-invoked successfully",
                    "graph_id": graph_id
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error re-invoking public graph permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/assistants/{assistant_id}/re-invoke")
async def re_invoke_public_assistant_permission(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Re-invoke a previously revoked public assistant permission."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        # Re-invoke by setting revoked_at back to NULL
        async with get_db_connection() as connection:
            result = await connection.execute(
                """
                UPDATE langconnect.public_assistant_permissions
                SET revoked_at = NULL, revoke_mode = NULL
                WHERE assistant_id = $1 AND revoked_at IS NOT NULL
                """,
                assistant_id
            )
            
            if "UPDATE 0" in result:
                raise HTTPException(status_code=404, detail="No revoked permission found for this assistant")
            
            return {"message": "Public assistant permission re-invoked successfully", "assistant_id": assistant_id}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error re-invoking public assistant permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# COLLECTION ENDPOINTS
# ============================================================================

@router.get("/collections", response_model=List[PublicCollectionPermissionItem])
async def list_public_collection_permissions(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """List all public collection permissions."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        async with get_db_connection() as connection:
            # Get public collection permissions with user info
            permissions = await connection.fetch(
                """
                SELECT 
                    pcp.id,
                    pcp.collection_id,
                    pcp.permission_level,
                    pcp.created_at,
                    pcp.revoked_at,
                    pcp.revoke_mode,
                    pcp.notes,
                    ur.display_name as created_by_display_name,
                    ur.email as created_by_email
                FROM langconnect.public_collection_permissions pcp
                LEFT JOIN langconnect.user_roles ur ON pcp.created_by::text = ur.user_id
                ORDER BY pcp.created_at DESC
                """
            )
            
        response = []
        for p in permissions:
            response.append(PublicCollectionPermissionItem(
                id=p["id"],
                collection_id=str(p["collection_id"]),
                permission_level=p["permission_level"],
                created_at=p["created_at"].isoformat() if p["created_at"] else None,
                revoked_at=p["revoked_at"].isoformat() if p["revoked_at"] else None,
                revoke_mode=p.get("revoke_mode"),
                notes=p["notes"],
                created_by=p.get("created_by_display_name") or "Unknown"
            ))
        return response

    except Exception as e:
        log.error(f"Error listing public collection permissions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/collections", response_model=Dict[str, Any])
async def create_public_collection_permission(
    request: CreatePublicCollectionRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Create a new public collection permission."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    # Validate permission level
    if request.permission_level not in ["viewer", "editor"]:
        raise HTTPException(status_code=400, detail="Invalid permission level. Must be 'viewer' or 'editor'.")

    try:
        # First verify the collection exists and get its details
        collections_manager = CollectionsManager(actor.identity)
        collection = await collections_manager.get(request.collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail=f"Collection '{request.collection_id}' not found")

        async with get_db_connection() as connection:
            # Use a transaction to ensure consistency
            async with connection.transaction():
                # Check if public permission already exists for this collection
                existing = await connection.fetchrow(
                    "SELECT id FROM langconnect.public_collection_permissions WHERE collection_id = $1::uuid AND revoked_at IS NULL",
                    request.collection_id
                )
                
                if existing:
                    raise HTTPException(status_code=409, detail="Public permission already exists for this collection")

                # Create the public collection permission
                result = await connection.fetchrow(
                    """
                    INSERT INTO langconnect.public_collection_permissions 
                    (collection_id, permission_level, created_by, notes)
                    VALUES ($1::uuid, $2, $3, $4)
                    RETURNING id, created_at
                    """,
                    request.collection_id, request.permission_level, actor.identity, request.notes
                )

                # Immediately grant this collection permission to all existing users
                granted_result = await connection.execute(
                    """
                    INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
                    SELECT ur.user_id, $1::uuid, $2, 'system:public'
                    FROM langconnect.user_roles ur
                    ON CONFLICT (collection_id, user_id) DO NOTHING
                    """,
                    request.collection_id, request.permission_level
                )
                
                # Extract number of users granted permission
                users_granted = 0
                if hasattr(granted_result, 'split'):
                    users_granted = int(granted_result.split()[-1]) if granted_result.split()[-1].isdigit() else 0

                log.info(f"User '{actor.identity}' created public permission for collection '{request.collection_id}' with level '{request.permission_level}' and granted to {users_granted} existing users")
                
                return {
                    "id": result["id"],
                    "collection_id": request.collection_id,
                    "collection_name": collection["name"],
                    "permission_level": request.permission_level,
                    "created_at": result["created_at"].isoformat(),
                    "users_granted": users_granted,
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating public collection permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/collections/{collection_id}")
async def revoke_public_collection_permission(
    collection_id: str,
    request: RevokeRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Revoke a public permission for a collection."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        async with get_db_connection() as connection:
            # First check if there's an active permission
            active_permission = await connection.fetchrow(
                "SELECT id FROM langconnect.public_collection_permissions WHERE collection_id = $1::uuid AND revoked_at IS NULL",
                collection_id
            )
            
            # If there's an active permission, revoke it normally
            if active_permission:
                async with connection.transaction():
                    # Mark the public permission as revoked
                    await connection.execute(
                        """
                        UPDATE langconnect.public_collection_permissions 
                        SET revoked_at = NOW(), revoke_mode = $1
                        WHERE collection_id = $2::uuid AND revoked_at IS NULL
                        """,
                        request.revoke_mode, collection_id
                    )
                    
                    revoked_count = 0
                    # If revoke_all mode, remove existing user permissions that were granted by public permission
                    if request.revoke_mode == 'revoke_all':
                        delete_result = await connection.execute(
                            "DELETE FROM langconnect.collection_permissions WHERE collection_id = $1::uuid AND granted_by = 'system:public'",
                            collection_id
                        )
                        
                        if hasattr(delete_result, 'split'):
                            revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0
                    
                    return {
                        "message": "Public collection permission revoked successfully",
                        "result": {
                            "collection_id": collection_id,
                            "status": "revoked",
                            "mode": request.revoke_mode,
                            "revoked_user_count": revoked_count
                        }
                    }
            
            # If no active permission, check for a revoked one that we might want to change mode
            revoked_permission = await connection.fetchrow(
                "SELECT id, revoke_mode FROM langconnect.public_collection_permissions WHERE collection_id = $1::uuid AND revoked_at IS NOT NULL",
                collection_id
            )
            
            if not revoked_permission:
                raise HTTPException(status_code=404, detail=f"No public permission found for collection_id: {collection_id}")
            
            # If we're trying to revoke_all on a future_only revoked permission, update it
            if request.revoke_mode == 'revoke_all' and revoked_permission['revoke_mode'] == 'future_only':
                # Update the revoke mode and remove existing user permissions
                await connection.execute(
                    "UPDATE langconnect.public_collection_permissions SET revoke_mode = 'revoke_all' WHERE collection_id = $1::uuid",
                    collection_id
                )
                
                # Remove existing user permissions that were granted by the public permission
                delete_result = await connection.execute(
                    "DELETE FROM langconnect.collection_permissions WHERE collection_id = $1::uuid AND granted_by = 'system:public'",
                    collection_id
                )
                
                revoked_count = 0
                if hasattr(delete_result, 'split'):
                    revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0
                
                return {
                    "message": "Public collection permission updated to revoke all users",
                    "result": {
                        "collection_id": collection_id,
                        "status": "revoked",
                        "mode": "revoke_all",
                        "revoked_user_count": revoked_count
                    }
                }
            else:
                raise HTTPException(status_code=400, detail=f"Permission already revoked with mode: {revoked_permission['revoke_mode']}")

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error revoking public collection permission for {collection_id} by {actor.identity}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/collections/{collection_id}/re-invoke")
async def re_invoke_public_collection_permission(
    collection_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """Re-invoke a previously revoked public collection permission and grant to all existing users."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        # Re-invoke by setting revoked_at back to NULL and grant to all existing users
        async with get_db_connection() as connection:
            async with connection.transaction():
                # First, get the permission level from the revoked public permission
                permission_info = await connection.fetchrow(
                    """
                    SELECT permission_level FROM langconnect.public_collection_permissions
                    WHERE collection_id = $1::uuid AND revoked_at IS NOT NULL
                    """,
                    collection_id
                )
                
                if not permission_info:
                    raise HTTPException(status_code=404, detail="No revoked permission found for this collection")
                
                permission_level = permission_info["permission_level"]
                
                # Re-invoke the public permission
                result = await connection.execute(
                    """
                    UPDATE langconnect.public_collection_permissions
                    SET revoked_at = NULL, revoke_mode = NULL
                    WHERE collection_id = $1::uuid AND revoked_at IS NOT NULL
                    """,
                    collection_id
                )
                
                if "UPDATE 0" in result:
                    raise HTTPException(status_code=404, detail="No revoked permission found for this collection")
                
                # Grant this collection permission to all existing users
                granted_result = await connection.execute(
                    """
                    INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
                    SELECT ur.user_id, $1::uuid, $2, 'system:public'
                    FROM langconnect.user_roles ur
                    ON CONFLICT (collection_id, user_id) DO NOTHING
                    """,
                    collection_id, permission_level
                )
                
                # Extract number of users granted permission
                users_granted = 0
                if hasattr(granted_result, 'split'):
                    users_granted = int(granted_result.split()[-1]) if granted_result.split()[-1].isdigit() else 0
                
                log.info(f"User '{actor.identity}' re-invoked public permission for collection '{collection_id}' with level '{permission_level}' and granted to {users_granted} existing users")
                
                return {
                    "message": "Public collection permission re-invoked successfully", 
                    "collection_id": collection_id,
                    "permission_level": permission_level,
                    "users_granted": users_granted
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error re-invoking public collection permission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 