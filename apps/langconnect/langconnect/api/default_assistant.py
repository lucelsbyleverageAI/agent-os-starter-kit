"""
Default assistant API endpoints for user's default assistant management.

This module provides endpoints for:
- GET /default-assistant - Get user's current default assistant
- PUT /default-assistant - Set/update user's default assistant
- DELETE /default-assistant - Clear user's default assistant
"""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from langconnect.auth import AuthenticatedUser, resolve_user
from langconnect.database import DefaultAssistantManager
from langconnect.models import (
    DefaultAssistantResponse,
    SetDefaultAssistantRequest,
    SetDefaultAssistantResponse,
)

# Set up logging
log = logging.getLogger(__name__)

router = APIRouter(prefix="/default-assistant", tags=["default-assistant"])


@router.get("", response_model=Optional[DefaultAssistantResponse])
async def get_default_assistant(
    user: Annotated[AuthenticatedUser, Depends(resolve_user)],
):
    """Get user's current default assistant.

    Returns:
        Default assistant information or null if no default is set
    """
    try:
        manager = DefaultAssistantManager(user.identity)
        default = await manager.get_default_assistant()

        if default:
            return DefaultAssistantResponse(**default)
        return None

    except Exception as e:
        log.error(f"Failed to get default assistant for user {user.identity}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve default assistant"
        )


@router.put("", response_model=SetDefaultAssistantResponse)
async def set_default_assistant(
    request: SetDefaultAssistantRequest,
    user: Annotated[AuthenticatedUser, Depends(resolve_user)],
):
    """Set or update user's default assistant.

    Args:
        request: Request containing assistant_id to set as default

    Returns:
        Updated default assistant information

    Raises:
        403: User doesn't have permission to the assistant
        404: Assistant doesn't exist
    """
    try:
        manager = DefaultAssistantManager(user.identity)
        result = await manager.set_default_assistant(request.assistant_id)

        return SetDefaultAssistantResponse(**result)

    except PermissionError as e:
        log.warning(f"Permission denied setting default assistant for user {user.identity}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        log.warning(f"Invalid assistant for default setting by user {user.identity}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log.error(f"Failed to set default assistant for user {user.identity}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default assistant"
        )


@router.delete("", response_model=dict[str, bool])
async def clear_default_assistant(
    user: Annotated[AuthenticatedUser, Depends(resolve_user)],
):
    """Clear user's default assistant.

    Returns:
        Success status indicating if default was cleared
    """
    try:
        manager = DefaultAssistantManager(user.identity)
        cleared = await manager.clear_default_assistant()

        return {"success": cleared}

    except Exception as e:
        log.error(f"Failed to clear default assistant for user {user.identity}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear default assistant"
        )
