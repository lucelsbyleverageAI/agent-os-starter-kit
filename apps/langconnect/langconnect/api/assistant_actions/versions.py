"""
Assistant version history endpoints: list versions and restore to previous versions.
"""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    AssistantVersionsResponse,
    AssistantRestoreRequest,
    AssistantRestoreResponse,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
from langconnect.services.version_service import VersionService, get_version_service
from langconnect.database.permissions import AssistantPermissionsManager

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/assistants/{assistant_id}/versions", response_model=AssistantVersionsResponse)
async def get_assistant_versions(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
    limit: int = 50,
    offset: int = 0,
) -> AssistantVersionsResponse:
    """
    Get version history for an assistant.

    Returns a list of all versions for the assistant, including:
    - Version number and timestamp
    - Configuration at that version
    - Optional commit message (if provided when saving)

    **Authorization:**
    - **All permission levels**: Viewers, editors, and owners can view version history
    - **Service Accounts**: Can view all assistant versions
    """
    try:
        log.info(f"Getting versions for assistant {assistant_id} by {actor.actor_type}:{actor.identity}")

        # Check permission (any level is sufficient for viewing versions)
        if actor.actor_type != "service":
            permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if not permission:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have access to this assistant"
                )

        # Get versions from service (no user_token needed - uses service account)
        version_service = get_version_service(langgraph_service)
        return await version_service.get_versions(
            assistant_id,
            user_token=None,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get versions for assistant {assistant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get version history: {str(e)}"
        )


@router.post("/assistants/{assistant_id}/restore", response_model=AssistantRestoreResponse)
async def restore_assistant_version(
    assistant_id: str,
    request: AssistantRestoreRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> AssistantRestoreResponse:
    """
    Restore an assistant to a previous version.

    Creates a NEW version with the configuration from the specified version.
    This preserves the complete version history (doesn't overwrite).

    **Authorization:**
    - **Editors and Owners**: Can restore to previous versions
    - **Viewers**: Cannot restore (read-only access)
    - **Service Accounts**: Can restore any assistant
    """
    try:
        log.info(
            f"Restoring assistant {assistant_id} to version {request.version} "
            f"by {actor.actor_type}:{actor.identity}"
        )

        # Check permission (must be editor or owner)
        if actor.actor_type != "service":
            permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if not permission:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have access to this assistant"
                )
            if permission not in ["owner", "editor"]:
                raise HTTPException(
                    status_code=403,
                    detail="You need editor or owner permission to restore versions"
                )

        user_id = actor.identity

        # Restore version (no user_token needed - uses service account)
        version_service = get_version_service(langgraph_service)
        return await version_service.restore_version(
            assistant_id,
            request.version,
            user_id=user_id,
            commit_message=request.commit_message,
            user_token=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to restore assistant {assistant_id} to version {request.version}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore version: {str(e)}"
        )
