"""Storage API endpoints for accessing images and files."""

import io
import logging
import os
from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
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


# Allowed MIME types for chat document uploads
CHAT_DOCUMENT_ALLOWED_TYPES = [
    # Documents
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # .pptx
    'application/msword',  # .doc
    'application/vnd.ms-excel',  # .xls
    'application/vnd.ms-powerpoint',  # .ppt
    # Text/Data
    'text/plain',
    'text/csv',
    'text/markdown',
]


@router.post("/upload-chat-document")
async def upload_chat_document(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    file: UploadFile = File(...),
) -> dict:
    """
    Upload a document for use in chat messages.

    The document is stored in the chat-uploads bucket with path: {user_id}/{timestamp}_{filename}
    This allows agents to access the original binary file in the sandbox for processing.

    Args:
        file: Document file to upload (PDF, DOCX, XLSX, PPTX, etc.)

    Returns:
        Dict with storage_path for use in message content blocks

    Raises:
        400: Invalid file type or size
        500: Upload failed
    """
    try:
        # Validate file type
        content_type = file.content_type

        if content_type not in CHAT_DOCUMENT_ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {content_type}. Allowed types: {', '.join(CHAT_DOCUMENT_ALLOWED_TYPES)}"
            )

        # Validate file size (50MB limit)
        file_data = await file.read()
        if len(file_data) > 52428800:  # 50MB in bytes
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 50MB limit"
            )

        # Upload to storage using the same chat_uploads method
        result = await storage_service.upload_chat_image(
            file_data=file_data,
            filename=file.filename,
            content_type=content_type,
            user_id=actor.identity,
        )

        logger.info(f"Uploaded chat document for user {actor.identity}: {result['storage_path']}")

        return {
            "storage_path": result["storage_path"],
            "bucket": result["bucket"],
            "filename": file.filename,
            "content_type": content_type,
            "file_size": len(file_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload chat document: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.post("/upload-support-image")
async def upload_support_image(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    file: UploadFile = File(...),
) -> dict:
    """
    Upload a screenshot for bug reports and feature requests.

    The image is stored in the support bucket with path: {user_id}/{timestamp}_{filename}
    Returns only the storage path (not base64), which will be converted to a signed URL at runtime.

    Args:
        file: Image file to upload

    Returns:
        Dict with storage_path for use in feedback screenshot_urls array

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
        result = await storage_service.upload_support_image(
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

        logger.info(f"Uploaded support screenshot for user {actor.identity}: {result['storage_path']}")

        return {
            "storage_path": result["storage_path"],
            "bucket": result["bucket"],
            "filename": file.filename,
            "preview_url": preview_url  # Temporary signed URL for immediate preview (localhost in dev)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload support screenshot: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload screenshot: {str(e)}"
        )


# ============================================================================
# Agent Output Endpoints - For Skills DeepAgent file sharing
# ============================================================================

# Allowed MIME types for agent outputs (broader than chat uploads)
AGENT_OUTPUT_ALLOWED_TYPES = [
    # Images
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    # Documents
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # .pptx
    'application/msword',  # .doc
    'application/vnd.ms-excel',  # .xls
    'application/vnd.ms-powerpoint',  # .ppt
    # Text/Data
    'text/plain', 'text/csv', 'text/markdown', 'text/html',
    'application/json', 'application/xml',
    # Fallback
    'application/octet-stream',
]


def get_mime_type_from_filename(filename: str) -> str:
    """Get MIME type from filename extension."""
    if not filename or '.' not in filename:
        return "application/octet-stream"

    ext = filename.rsplit('.', 1)[-1].lower()
    mime_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
        "csv": "text/csv",
        "txt": "text/plain",
        "md": "text/markdown",
        "json": "application/json",
        "html": "text/html",
        "xml": "application/xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }
    return mime_types.get(ext, "application/octet-stream")


@router.post("/upload-agent-output")
async def upload_agent_output(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    filename: str = Form(None),
) -> dict:
    """
    Upload a file created by an agent to storage.

    Used by the publish_file_to_user tool in Skills DeepAgent to make
    sandbox files available for user preview and download.

    Args:
        file: File to upload (from sandbox)
        thread_id: Thread ID for storage organization
        filename: Optional filename override

    Returns:
        Dict with storage_path and metadata

    Raises:
        400: Invalid file type or size
        500: Upload failed
    """
    try:
        # Validate file type
        content_type = file.content_type or "application/octet-stream"

        # Be lenient with content types - allow most things
        # The agent is creating these files, so we trust them more

        # Validate file size (50MB limit)
        file_data = await file.read()
        if len(file_data) > 52428800:  # 50MB in bytes
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 50MB limit"
            )

        actual_filename = filename or file.filename or "output"

        # Upload to storage
        result = await storage_service.upload_agent_output(
            file_data=file_data,
            filename=actual_filename,
            content_type=content_type,
            user_id=actor.identity,
            thread_id=thread_id,
        )

        logger.info(
            f"Uploaded agent output for user {actor.identity}, "
            f"thread {thread_id}: {result['storage_path']}"
        )

        return {
            "storage_path": result["storage_path"],
            "bucket": result["bucket"],
            "filename": actual_filename,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload agent output: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {str(e)}"
        )


@router.get("/thread-file")
async def get_thread_file(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    storage_path: str = Query(..., description="Storage path (user_id/... or user_id/thread_id/...)"),
    bucket: str = Query("agent-outputs", description="Storage bucket"),
) -> StreamingResponse:
    """
    Download a file from storage.

    Validates user owns the file before allowing access.
    Uses permanent storage path (not signed URL) to ensure links don't expire.

    Supports two path formats:
    - agent-outputs bucket: user_id/thread_id/filename (3+ parts)
    - chat-uploads bucket: user_id/timestamp_filename (2 parts)

    Args:
        storage_path: Storage path
        bucket: Storage bucket (default: agent-outputs)

    Returns:
        File content as streaming response

    Raises:
        400: Invalid storage path format
        403: User doesn't own this file
        404: File not found
    """
    try:
        # Validate path format based on bucket
        parts = storage_path.split("/")

        # Different path formats for different buckets
        if bucket == "chat-uploads":
            # chat-uploads format: {user_id}/{timestamp}_{filename}
            if len(parts) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid storage path format. Expected: user_id/filename"
                )
            path_user_id = parts[0]
            filename = parts[-1]
        else:
            # agent-outputs format: {user_id}/{thread_id}/{filename}
            if len(parts) < 3:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid storage path format. Expected: user_id/thread_id/filename"
                )
            path_user_id = parts[0]
            filename = parts[-1]

        # Verify user owns this file (or is service account)
        # Security: Storage path always starts with user_id
        # Checking path_user_id matches actor.identity ensures users can only
        # access their own files. No additional thread lookup needed.
        if not actor.is_service_account:
            if path_user_id != actor.identity:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied - you don't own this file"
                )

        # Download file from storage
        if bucket == "agent-outputs":
            file_data = await storage_service.download_agent_output(storage_path)
        elif bucket == "chat-uploads":
            file_data = await storage_service.download_chat_upload(storage_path)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported bucket: {bucket}"
            )

        # Determine MIME type
        mime_type = get_mime_type_from_filename(filename)

        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, max-age=3600"  # Cache for 1 hour
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download thread file: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {str(e)}"
        )