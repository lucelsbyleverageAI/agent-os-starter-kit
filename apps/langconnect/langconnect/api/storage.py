"""Storage API endpoints for accessing images and files."""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.database.collections import CollectionsManager
from langconnect.services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/signed-url")
async def get_signed_url(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    storage_path: str = Query(..., description="Storage URI (storage://collections/...)")
) -> dict:
    """
    Get a signed URL for accessing a file in storage.

    Requires user to have at least 'viewer' permission on the collection.

    Args:
        storage_path: Storage URI in format storage://collections/{collection_uuid}/{filename}

    Returns:
        Dict with signed_url and expires_in seconds

    Raises:
        400: Invalid storage path format
        403: User doesn't have permission to access this collection
        404: File not found
    """
    try:
        # Parse storage URI
        parsed = storage_service.parse_storage_uri(storage_path)
        file_path = parsed["file_path"]
        bucket = parsed["bucket"]

        # Extract collection UUID from file path (first folder)
        # Format: {collection_uuid}/{timestamp}_{filename}
        path_parts = file_path.split("/")
        if len(path_parts) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid storage path format: {storage_path}"
            )

        collection_uuid = path_parts[0]

        # Check if user has permission to access this collection
        collections_manager = CollectionsManager(actor.identity)
        collection = await collections_manager.get(collection_uuid)

        if not collection:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access this collection"
            )

        # Generate signed URL
        signed_url = await storage_service.get_signed_url(file_path)

        return {
            "signed_url": signed_url,
            "expires_in": storage_service.signed_url_expiry,
            "storage_path": storage_path
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid storage path: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate signed URL: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate signed URL: {str(e)}"
        )
