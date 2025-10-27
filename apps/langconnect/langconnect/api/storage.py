"""Storage API endpoints for accessing images and files."""

import logging
import os
from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.database.collections import CollectionsManager
from langconnect.services.storage_service import storage_service

logger = logging.getLogger(__name__)


def fix_storage_url_for_development(url: str) -> str:
    """
    Replace kong:8000 with localhost:8000 in development environments.

    This is needed because:
    - Supabase in Docker uses SUPABASE_URL=http://kong:8000 for internal communication
    - Browser cannot resolve 'kong' hostname in development
    - localhost:8000 works for both Docker and local development
    """
    # Check if we're in development mode
    is_development = os.getenv("ENVIRONMENT", "development") == "development"

    if is_development and "kong:8000" in url:
        return url.replace("kong:8000", "localhost:8000")

    return url

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

        # Fix URL for development (replace kong with localhost)
        signed_url = fix_storage_url_for_development(signed_url)

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


@router.post("/upload-chat-image")
async def upload_chat_image(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    file: UploadFile = File(...),
) -> dict:
    """
    Upload an image for use in chat messages.

    The image is stored in the chat-uploads bucket with path: {user_id}/{timestamp}_{filename}
    Returns only the storage path (not base64), which will be converted to a signed URL at runtime.

    Args:
        file: Image file to upload

    Returns:
        Dict with storage_path for use in message content blocks

    Raises:
        400: Invalid file type or size
        500: Upload failed
    """
    try:
        # Validate file type
        content_type = file.content_type
        allowed_types = [
            'image/jpeg', 'image/png', 'image/gif',
            'image/webp', 'image/bmp', 'image/tiff'
        ]

        if content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {content_type}. Allowed types: {', '.join(allowed_types)}"
            )

        # Validate file size (50MB limit)
        file_data = await file.read()
        if len(file_data) > 52428800:  # 50MB in bytes
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 50MB limit"
            )

        # Upload to storage
        result = await storage_service.upload_chat_image(
            file_data=file_data,
            filename=file.filename,
            content_type=content_type,
            user_id=actor.identity,
        )

        # Generate signed URL for preview (30 minutes expiry)
        signed_url = await storage_service.get_signed_url(
            file_path=result["storage_path"],
            bucket=result["bucket"],
            expiry_seconds=1800
        )

        # Fix URL for development (replace kong with localhost)
        preview_url = fix_storage_url_for_development(signed_url)

        logger.info(f"Uploaded chat image for user {actor.identity}: {result['storage_path']}")

        return {
            "storage_path": result["storage_path"],
            "bucket": result["bucket"],
            "filename": file.filename,
            "preview_url": preview_url  # Temporary signed URL for immediate preview (localhost in dev)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload chat image: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload image: {str(e)}"
        )