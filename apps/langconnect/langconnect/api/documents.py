"""Document API endpoints for full document operations (not chunks/embeddings)."""

import logging
import os
import time
import uuid
from typing import Annotated, Any, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, File, Form, UploadFile
from pydantic import BaseModel
import sentry_sdk

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.database.collections import Collection, CollectionsManager
from langconnect.database.document import DocumentManager
 
from langconnect.services.enhanced_document_processor import EnhancedDocumentProcessor
from langconnect.services.job_service import job_service
from langconnect.models.job import JobCreate, JobSubmissionResponse, JobType, ProcessingOptions, TextExtractionResponse
from langconnect.services.pymupdf_extractor_service import pymupdf_extractor
from langconnect.database.collections import CollectionPermissionsManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

# Special collection ID for text extraction jobs that don't belong to a specific collection
TEXT_EXTRACTION_COLLECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# Response Models
class DocumentSummary(BaseModel):
    """Summary information for a document."""
    id: str
    title: str
    description: str
    source_type: str
    source_name: Optional[str] = None
    content_length: int
    word_count: Optional[int] = None
    created_at: str
    updated_at: str
    chunk_count: Optional[int] = None
    metadata: dict[str, Any]  # Full metadata including file_type, storage_path for images


class DocumentDetail(BaseModel):
    """Detailed document information including content."""
    id: str
    collection_id: str
    title: str
    description: str
    content: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    chunk_count: Optional[int] = None
    chunks: Optional[List[dict[str, Any]]] = None  # Optional chunks list


class DocumentListResponse(BaseModel):
    """Response for document listing."""
    documents: List[DocumentSummary]
    total: int
    limit: int
    offset: int
    has_more: bool
    collection_uses_document_model: bool


class TextExtractionResponse(BaseModel):
    """Response model for text extraction."""
    
    success: bool
    content: str
    metadata: dict[str, Any] = {}
    processing_time_seconds: float = 0.0
    source_type: str = ""
    error_message: Optional[str] = None


@router.get(
    "/collections/{collection_id}/documents",
    response_model=DocumentListResponse
)
async def list_documents(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List full documents in a collection (not chunks). For chunks/embeddings, use /chunks endpoint."""
    
    sentry_sdk.add_breadcrumb(
        category="api.request",
        data={
            "endpoint": "list_documents",
            "collection_id": str(collection_id),
            "actor_type": actor.actor_type,
            "limit": limit,
            "offset": offset
        },
        level="info"
    )
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    # Use document model exclusively
    document_manager = collection.get_document_manager()
    documents_data, total = await document_manager.list_documents(
        limit=limit, 
        offset=offset, 
        include_content=False
    )
    
    documents = []
    for doc_data in documents_data:
        # Chunk count is now included in the document data from the optimized query
        chunk_count = doc_data.get("chunk_count", 0)
        
        documents.append(DocumentSummary(
            id=doc_data["id"],
            title=doc_data["metadata"].get("title", "Untitled"),
            description=doc_data["metadata"].get("description", ""),
            source_type=doc_data["metadata"].get("source_type", "unknown"),
            source_name=doc_data["metadata"].get("original_filename") or doc_data["metadata"].get("url"),
            content_length=doc_data["metadata"].get("content_length", 0),
            word_count=doc_data["metadata"].get("word_count"),
            created_at=doc_data["created_at"],
            updated_at=doc_data["updated_at"],
            chunk_count=chunk_count,
            metadata=doc_data["metadata"]  # Include full metadata for frontend (contains file_type, storage_path for images)
        ))
    
    return DocumentListResponse(
        documents=documents,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(documents) < total,
        collection_uses_document_model=True
    )


@router.get(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=DocumentDetail
)
async def get_document_detail(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    document_id: str,
    include_chunks: bool = Query(False, description="Include all chunks/embeddings for this document"),
):
    """Get full document details including content."""
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    # Use document model exclusively
    document_manager = collection.get_document_manager()
    doc_data = await document_manager.get_document(document_id)
    
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get chunk count and optionally chunk details
    chunks = await document_manager.get_document_chunks(document_id)
    chunk_details = None
    
    if include_chunks:
        # Format chunks for response
        chunk_details = []
        for chunk in chunks:
            content = chunk.get("content", "")
            chunk_details.append({
                "id": chunk.get("id"),
                "content": content,
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "content_length": len(content),
                "metadata": chunk.get("metadata", {}),
                "embedding": chunk.get("embedding") if chunk.get("embedding") else None
            })
    
    return DocumentDetail(
        id=doc_data["id"],
        collection_id=doc_data["collection_id"],
        title=doc_data["metadata"].get("title", "Untitled"),
        description=doc_data["metadata"].get("description", ""),
        content=doc_data["content"],
        metadata=doc_data["metadata"],
        created_at=doc_data["created_at"],
        updated_at=doc_data["updated_at"],
        chunk_count=len(chunks),
        chunks=chunk_details
    )


# Document search removed - use /collections/{collection_id}/chunks/search for semantic search over embeddings
# For document-level search (by title, filename, etc.), use the list endpoint with filters


@router.patch(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=dict[str, bool]
)
async def update_document_metadata(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    document_id: str,
    title: str = Form(..., description="Document title"),
    description: str = Form(default="", description="Document description"),
):
    """Update document title and description metadata."""
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    # Check edit permissions
    permissions_manager = CollectionPermissionsManager(effective_user_id)
    permission_level = await permissions_manager.get_user_permission_level(str(collection_id))
    if permission_level not in ["owner", "editor"]:
        raise HTTPException(
            status_code=403,
            detail="Edit permission required for this collection"
        )
    
    # Get document manager
    collection = Collection(str(collection_id), effective_user_id)
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    document_manager = collection.get_document_manager()
    
    # Get current document to merge metadata
    current_doc = await document_manager.get_document(document_id)
    if not current_doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Update metadata with new title and description
    updated_metadata = current_doc.get("metadata", {}).copy()
    updated_metadata["title"] = title
    updated_metadata["name"] = title  # Keep both for compatibility
    updated_metadata["description"] = description
    
    # Update the document
    success = await document_manager.update_document_metadata(document_id, updated_metadata)
    
    return {"success": success}


@router.put(
    "/collections/{collection_id}/documents/{document_id}/content",
    response_model=JobSubmissionResponse,
    status_code=202,
)
async def update_document_content(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    document_id: str,
    content: str = Form(..., description="New document content"),
):
    """Update document content and trigger re-chunking/re-embedding.

    This endpoint:
    1. Updates the document content
    2. Deletes existing chunks/embeddings
    3. Creates a background job to re-chunk and re-embed the document

    Returns a job ID for tracking the re-processing status.
    """

    sentry_sdk.add_breadcrumb(
        category="api.request",
        data={
            "endpoint": "update_document_content",
            "collection_id": str(collection_id),
            "document_id": document_id,
            "actor_type": actor.actor_type,
            "content_length": len(content)
        },
        level="info"
    )

    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    # Check edit permissions
    permissions_manager = CollectionPermissionsManager(effective_user_id)
    permission_level = await permissions_manager.get_user_permission_level(str(collection_id))
    if permission_level not in ["owner", "editor"]:
        raise HTTPException(
            status_code=403,
            detail="Edit permission required for this collection"
        )

    # Get document manager
    collection = Collection(str(collection_id), effective_user_id)
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True

    document_manager = collection.get_document_manager()

    # Get current document to preserve metadata
    current_doc = await document_manager.get_document(document_id)
    if not current_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        # Update document content (this sets processing_status to 'pending')
        update_success = await document_manager.update_document_content(document_id, content)

        if not update_success:
            raise HTTPException(status_code=500, detail="Failed to update document content")

        # Delete existing embeddings/chunks
        deleted_count = await document_manager.delete_document_embeddings(document_id)
        logger.info(f"Deleted {deleted_count} embeddings for document {document_id}")

        # Get processing options from document metadata or use defaults
        metadata = current_doc.get("metadata", {})
        processing_mode = metadata.get("processing_mode", "balanced")
        chunking_strategy = metadata.get("chunking_strategy", "markdown_aware")

        processing_options = ProcessingOptions(
            processing_mode=processing_mode,
            image_processing="placeholders",
            chunking_strategy=chunking_strategy,
            ocr_enabled=True,
            extract_tables=True,
            extract_figures=True,
        )

        # Create job for re-processing
        input_data = {
            "document_id": document_id,
            "collection_id": str(collection_id),
            "title": metadata.get("title", "Untitled"),
            "description": f"Re-processing document after content update",
        }

        job_data = JobCreate(
            user_id=effective_user_id,
            collection_id=collection_id,
            job_type=JobType.REPROCESS_DOCUMENT,
            title=f"Re-processing: {metadata.get('title', 'Untitled')}",
            description="Re-chunking and re-embedding document after content update",
            processing_options=processing_options,
            input_data=input_data
        )

        job = await job_service.create_job(job_data, effective_user_id)
        started = await job_service.start_job_processing(job.id)

        return JobSubmissionResponse(
            job_id=job.id,
            status=job.status,
            message="Document content updated. Re-processing chunks..." if started else "Content updated but re-processing failed to start",
            estimated_duration_seconds=job.estimated_duration_seconds
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update document content: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update document content: {str(e)}"
        )


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=dict[str, bool]
)
async def delete_document(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    document_id: str,
):
    """Delete a document and its associated chunks.

    If the document has an associated file in storage (e.g., images),
    it will be deleted from storage as well.
    """

    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)

    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True

    # Use document model exclusively
    document_manager = collection.get_document_manager()

    # Get document metadata before deleting to check for storage files
    doc_data = await document_manager.get_document(document_id)

    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if document has a storage path (for images or uploaded files)
    storage_path = doc_data.get("metadata", {}).get("storage_path")

    if storage_path:
        # Delete from storage first
        from langconnect.services.storage_service import storage_service

        try:
            parsed = storage_service.parse_storage_uri(storage_path)
            await storage_service.delete_file(parsed["file_path"])
            logger.info(f"Deleted storage file: {storage_path}")
        except Exception as e:
            # Log error but don't fail the deletion - file might already be gone
            logger.warning(f"Failed to delete storage file {storage_path}: {e}")

    # Delete document from database
    success = await document_manager.delete_document(document_id)

    return {"success": success}


@router.put(
    "/collections/{collection_id}/documents/{document_id}/image",
    response_model=dict
)
async def replace_document_image(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    document_id: str,
    file: UploadFile = File(...),
):
    """
    Replace the image file for an image document.

    This endpoint:
    1. Verifies the document is an image type
    2. Deletes the old image from storage
    3. Uploads the new image to storage
    4. Runs vision AI analysis on the new image
    5. Updates document metadata and content
    6. Re-chunks and re-embeds the document

    Requires 'editor' or 'owner' permission on the collection.
    """
    from langconnect.services.storage_service import storage_service
    from langconnect.services.vision_analysis_service import vision_analysis_service

    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)

    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True

    # Check user has editor or owner permission
    permission_level = collection_details.get("permission_level") if isinstance(actor, ServiceAccount) else None
    if not permission_level:
        # Get user's permission level
        collections_manager = CollectionsManager(effective_user_id)
        collection_details = await collections_manager.get(str(collection_id))
        permission_level = collection_details.get("permission_level")

    if permission_level not in ["editor", "owner"]:
        raise HTTPException(
            status_code=403,
            detail="You need editor or owner permission to replace images"
        )

    # Get document
    document_manager = collection.get_document_manager()
    doc_data = await document_manager.get_document(document_id)

    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify it's an image document
    if doc_data.get("metadata", {}).get("file_type") != "image":
        raise HTTPException(
            status_code=400,
            detail="This endpoint only works for image documents"
        )

    old_storage_path = doc_data.get("metadata", {}).get("storage_path")
    if not old_storage_path:
        raise HTTPException(
            status_code=400,
            detail="Document missing storage_path metadata"
        )

    # Read new image content
    image_bytes = await file.read()
    filename = file.filename or "image.jpg"
    content_type = file.content_type or "image/jpeg"

    # Determine image format
    image_format = 'jpeg'
    if content_type:
        if 'png' in content_type:
            image_format = 'png'
        elif 'webp' in content_type:
            image_format = 'webp'
        elif 'gif' in content_type:
            image_format = 'gif'

    logger.info(f"Replacing image for document {document_id} with {filename}")

    try:
        # Run vision AI analysis on new image
        logger.info(f"Analyzing new image with AI vision")
        vision_metadata = await vision_analysis_service.analyze_image(
            image_data=image_bytes,
            image_format=image_format,
            fallback_title=os.path.splitext(filename)[0]
        )

        # Delete old image from storage
        try:
            parsed = storage_service.parse_storage_uri(old_storage_path)
            await storage_service.delete_file(parsed["file_path"])
            logger.info(f"Deleted old image: {old_storage_path}")
        except Exception as e:
            logger.warning(f"Failed to delete old image (continuing anyway): {e}")

        # Upload new image to storage
        logger.info(f"Uploading new image to storage")
        storage_info = await storage_service.upload_image(
            file_data=image_bytes,
            filename=filename,
            content_type=content_type,
            collection_uuid=str(collection_id)
        )

        # Update document metadata
        new_metadata = {
            **doc_data.get("metadata", {}),
            "name": vision_metadata.title,
            "title": vision_metadata.title,
            "description": vision_metadata.short_description,
            "storage_path": storage_info["storage_path"],
            "storage_bucket": storage_info["bucket"],
            "storage_file_path": storage_info["file_path"],
            "content_type": content_type,
            "image_format": image_format,
        }

        await document_manager.update_document_metadata(document_id, new_metadata)

        # Update document content with detailed description
        # This will trigger re-chunking and re-embedding
        await document_manager.update_document_content(
            document_id,
            vision_metadata.detailed_description
        )

        logger.info(f"Successfully replaced image for document {document_id}")

        return {
            "success": True,
            "message": "Image replaced successfully",
            "document_id": document_id,
            "metadata": {
                "title": vision_metadata.title,
                "description": vision_metadata.short_description,
                "storage_path": storage_info["storage_path"]
            }
        }

    except Exception as e:
        logger.error(f"Failed to replace image: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to replace image: {str(e)}"
        )


# =====================
# Document Upload Endpoints (moved from collections)
# =====================

@router.post(
    "/collections/{collection_id}/documents",
    response_model=JobSubmissionResponse,
    status_code=202,
)
async def upload_documents(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    
    # Job-level metadata (for batch tracking)
    job_title: str = Form(default=""),
    job_description: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    urls: str = Form(default=""),
    text_content: str = Form(default=""),
    processing_mode: str = Form(
        default="balanced", 
        description="Processing mode: 'fast' (standard processing with table extraction, no OCR), 'balanced' (OCR processing for scanned documents with table extraction)"
    ),
    image_processing: str = Form(default="placeholders"),
    chunking_strategy: str = Form(default="markdown_aware"),
    ocr_enabled: bool = Form(default=True),
    extract_tables: bool = Form(default=True),
    extract_figures: bool = Form(default=True),
    use_ai_metadata: bool = Form(default=False, description="Use AI to generate document names and descriptions"),
):
    """Upload and process documents using enhanced processing pipeline.

    Processing Modes:
    - **fast**: Standard processing with table extraction but no OCR (faster, for digital documents)
    - **balanced**: OCR processing for scanned documents with table extraction (recommended for mixed document types)

    AI Metadata:
    - **use_ai_metadata**: When enabled, uses OpenAI to generate descriptive names and summaries for documents based on their content
    """
    
    sentry_sdk.add_breadcrumb(
        category="api.request",
        data={
            "endpoint": "upload_documents",
            "collection_id": str(collection_id),
            "actor_type": actor.actor_type,
            "file_count": len(files),
            "has_urls": bool(urls.strip()),
            "has_text_content": bool(text_content.strip()),
            "processing_mode": processing_mode
        },
        level="info"
    )
    
    # Validate input - at least one source required
    if not files and not urls.strip() and not text_content.strip():
        
        raise HTTPException(
            status_code=400,
            detail="At least one input source (files, URLs, or text) is required"
        )
    
    # Service account handling (consistent with existing pattern)
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity
    
    # Check edit permissions
    permissions_manager = CollectionPermissionsManager(effective_user_id)
    permission_level = await permissions_manager.get_user_permission_level(str(collection_id))
    if permission_level not in ["owner", "editor"]:
        
        raise HTTPException(
            status_code=403,
            detail="Edit permission required for this collection"
        )
    
    try:
        # Prepare processing options
        processing_options = ProcessingOptions(
            processing_mode=processing_mode,
            image_processing=image_processing,
            chunking_strategy=chunking_strategy,
            ocr_enabled=ocr_enabled,
            extract_tables=extract_tables,
            extract_figures=extract_figures,
            use_ai_metadata=use_ai_metadata,
        )
        
        # Generate smart defaults for job title and description if not provided
        if not job_title.strip():
            if files:
                job_title = f"Upload of {len(files)} file(s)"
                if len(files) == 1:
                    job_title = f"Upload: {files[0].filename}"
            elif urls.strip():
                url_list = [u.strip() for u in urls.split(",") if u.strip()]
                job_title = f"Import from {len(url_list)} URL(s)"
                if len(url_list) == 1:
                    job_title = f"Import: {url_list[0][:50]}..."
            elif text_content.strip():
                job_title = f"Text content: {text_content[:30]}..."
            else:
                job_title = "Document upload"
        
        if not job_description.strip():
            job_description = f"Processed with {processing_mode} mode"
        
        # Prepare input data for job
        input_data = {
            "title": job_title,
            "description": "",
        }
        
        # Add file information
        if files:
            # Store only file metadata in input_data, not content
            input_data["files"] = [
                {
                    "filename": f.filename,
                    "content_type": f.content_type,
                    "size": f.size if hasattr(f, 'size') else None,
                }
                for f in files
            ]
        
        # Add URLs
        if urls.strip():
            input_data["urls"] = [url.strip() for url in urls.split(",") if url.strip()]
        
        # Add text content
        if text_content.strip():
            input_data["text_content"] = text_content.strip()
        
        # Determine job type based on input
        # Note: TEXT_PROCESSING is reserved for chat text extraction (which doesn't save to collection)
        # For uploading text to a collection, use DOCUMENT_PROCESSING
        if files:
            job_type = JobType.DOCUMENT_PROCESSING
        elif input_data.get("urls"):
            # Check if any URLs are YouTube
            youtube_urls = [url for url in input_data["urls"] if "youtube.com" in url or "youtu.be" in url]
            if youtube_urls:
                job_type = JobType.YOUTUBE_PROCESSING
            else:
                job_type = JobType.URL_PROCESSING
        elif input_data.get("text_content"):
            # Use DOCUMENT_PROCESSING for text uploads to collection
            # (TEXT_PROCESSING is for chat feature only)
            job_type = JobType.DOCUMENT_PROCESSING
        else:
            job_type = JobType.DOCUMENT_PROCESSING
        
        # For file processing, convert UploadFile objects to serializable format for background job
        # But don't store the file content in input_data to keep database lightweight
        if files:
            import base64
            file_data = []
            total_size = 0
            for f in files:
                content = await f.read()
                total_size += len(content)
                # Convert to base64 for JSON serialization
                content_b64 = base64.b64encode(content).decode('utf-8')
                file_data.append({
                    "filename": f.filename,
                    "content_b64": content_b64,
                    "content_type": f.content_type,
                    "size": len(content)
                })
                await f.seek(0)  # Reset for any future reads
                
            # Store file metadata only in input_data (not the content)
            input_data["files"] = [
                {
                    "filename": f["filename"],
                    "content_type": f["content_type"],
                    "size": f["size"]
                }
                for f in file_data
            ]
            input_data["total_file_size"] = total_size
            
            
        
        # Use job title and description directly
        final_job_title = job_title or "Document processing"
        final_job_description = job_description or "Processing uploaded documents and content"
        
        # Create background job for all processing types (files, URLs, text)
        job_data = JobCreate(
            user_id=effective_user_id,
            collection_id=collection_id,
            job_type=job_type,
            title=final_job_title,
            description=final_job_description,
            processing_options=processing_options,
            input_data=input_data
        )
        
        job = await job_service.create_job(job_data, effective_user_id)
        
        # Pass the full file data (with content) to the job processor, but it won't be stored in DB
        if files and 'file_data' in locals():
            started = await job_service.start_job_processing(job.id, runtime_data={"files": file_data})
        else:
            started = await job_service.start_job_processing(job.id)
        
        
        
        return JobSubmissionResponse(
            job_id=job.id,
            status=job.status,
            message="Document processing job created and started" if started else "Job created but failed to start",
            estimated_duration_seconds=job.estimated_duration_seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create document processing job: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create document processing job: {str(e)}"
        )


@router.post(
    "/collections/{collection_id}/documents/batch",
    response_model=JobSubmissionResponse,
    status_code=202,
)
async def upload_documents_batch(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    
    batch_data: str = Form(..., description="JSON array of batch items"),
    processing_mode: str = Form(
        default="balanced", 
        description="Processing mode: 'fast' (standard processing with table extraction, no OCR), 'balanced' (OCR processing for scanned documents with table extraction)"
    ),
    image_processing: str = Form(default="placeholders"),
    chunking_strategy: str = Form(default="markdown_aware"),
):
    """Process a batch of mixed documents (files, URLs, YouTube, text) in a single job.
    
    Batch data should be a JSON array of objects with:
    - type: "file" | "url" | "youtube" | "text"
    - title: string
    - description: string (optional)
    - For files: filename: string (must exist in test files)
    - For URLs/YouTube: url: string
    - For text: content: string
    """
    
    # Service account handling
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity
    
    # Check edit permissions
    permissions_manager = CollectionPermissionsManager(effective_user_id)
    permission_level = await permissions_manager.get_user_permission_level(str(collection_id))
    if permission_level not in ["owner", "editor"]:
        
        raise HTTPException(
            status_code=403,
            detail="Edit permission required for this collection"
        )
    
    try:
        # Parse batch data
        import json
        batch_items = json.loads(batch_data)
        
        if not batch_items:
            raise HTTPException(status_code=400, detail="Batch data cannot be empty")
        
        # Prepare processing options
        processing_options = ProcessingOptions(
            processing_mode=processing_mode,
            image_processing=image_processing,
            chunking_strategy=chunking_strategy,
            ocr_enabled=True,
            extract_tables=True,
            extract_figures=True,
        )
        
        # Prepare input data for job
        input_data = {
            "batch_items": batch_items,
            "title": f"Batch Processing ({len(batch_items)} items)",
            "description": f"Batch processing of {len(batch_items)} mixed documents",
        }
        
        # Create background job
        job_data = JobCreate(
            user_id=effective_user_id,
            collection_id=collection_id,
            job_type=JobType.DOCUMENT_PROCESSING,  # Generic type for batch
            title=input_data["title"],
            description=input_data["description"],
            processing_options=processing_options,
            input_data=input_data
        )
        
        job = await job_service.create_job(job_data, effective_user_id)
        started = await job_service.start_job_processing(job.id)
        
        
        
        return JobSubmissionResponse(
            job_id=job.id,
            status=job.status,
            message=f"Batch processing job created for {len(batch_items)} items" + (" and started" if started else " but failed to start"),
            estimated_duration_seconds=job.estimated_duration_seconds
        )
        
    except json.JSONDecodeError as e:
        
        raise HTTPException(status_code=400, detail=f"Invalid JSON in batch_data: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create batch processing job: {str(e)}"
        )


# =====================
# Text Extraction Endpoints (for Chat Feature)
# =====================

@router.post("/documents/extract/text", response_model=JobSubmissionResponse | TextExtractionResponse)
async def extract_text(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],

    file: Optional[UploadFile] = File(None),
    url: str = Form(default=""),
    processing_mode: str = Form(
        default="balanced",
        description="Processing mode: 'quick' (fast PyMuPDF extraction for PDFs, synchronous), 'fast' (Dockling without OCR, async), 'balanced' (Dockling with table extraction, async)"
    ),
    include_metadata: bool = Form(default=True),
):
    """Extract text from files or URLs for chat feature.

    Processing Modes:
    - **quick**: Ultra-fast synchronous extraction using PyMuPDF (PDFs only, returns immediately)
    - **fast**: Standard Dockling processing with table extraction but no OCR (async job)
    - **balanced**: Full Dockling processing for complex documents (async job)

    For 'quick' mode with PDFs, returns TextExtractionResponse directly (200).
    For all other modes, returns JobSubmissionResponse for async polling (202).
    """
    
    # Validate input - exactly one source required
    if not file and not url.strip():
        raise HTTPException(
            status_code=400,
            detail="Either file or URL must be provided"
        )
    
    if file and url.strip():
        raise HTTPException(
            status_code=400,
            detail="Provide either file or URL, not both"
        )

    # Quick mode: synchronous PyMuPDF extraction for PDFs
    if processing_mode == "quick" and file:
        content_type = file.content_type or ""
        filename = file.filename or ""

        # Only use quick mode for PDFs
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            start_time = time.time()
            try:
                content = await file.read()
                result = pymupdf_extractor.extract_text_from_bytes(content)
                processing_time = time.time() - start_time

                if result.success:
                    return TextExtractionResponse(
                        success=True,
                        content=result.content,
                        metadata={
                            "filename": filename,
                            "page_count": result.page_count,
                            "content_length": len(result.content),
                            "extraction_method": "pymupdf_quick",
                        },
                        processing_time_seconds=processing_time,
                        source_type="pdf",
                    )
                else:
                    return TextExtractionResponse(
                        success=False,
                        content="",
                        error_message=result.error_message,
                        processing_time_seconds=processing_time,
                        source_type="pdf",
                    )
            except Exception as e:
                logger.exception("Quick PDF extraction failed")
                return TextExtractionResponse(
                    success=False,
                    content="",
                    error_message=str(e),
                    processing_time_seconds=time.time() - start_time,
                    source_type="pdf",
                )

    # Fall through to async job flow for non-quick modes or non-PDF files
    try:
        # For service accounts, we need a dummy collection for job processing
        # In practice, text extraction jobs could be collection-independent
        effective_user_id = actor.identity if not isinstance(actor, ServiceAccount) else "text-extraction-service"
        
        # Prepare processing options for text extraction only
        processing_options = ProcessingOptions(
            processing_mode=processing_mode,
            image_processing="placeholders",  # Fast image handling for text extraction
            chunking_strategy="none",  # No chunking needed for text extraction
            ocr_enabled=True,
            extract_tables=True,
            extract_figures=False,  # Skip figure analysis for speed
        )
        
        # Prepare input data for job
        if file:
            # Convert file to base64 for background processing
            import base64
            content = await file.read()
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            input_data = {
                "files": [{
                    "filename": file.filename,
                    "content_b64": content_b64,
                    "content_type": file.content_type,
                    "size": len(content)
                }],
                "title": f"Text extraction from {file.filename}",
                "description": "Text extraction for chat feature",
                "is_text_extraction": True,
                "include_metadata": include_metadata
            }
            job_type = JobType.TEXT_PROCESSING
        else:
            # Determine if URL is YouTube
            if "youtube.com" in url or "youtu.be" in url:
                job_type = JobType.YOUTUBE_PROCESSING
            else:
                job_type = JobType.URL_PROCESSING
            
            input_data = {
                "urls": [url.strip()],
                "title": f"Text extraction from {url}",
                "description": "Text extraction for chat feature",
                "is_text_extraction": True,
                "include_metadata": include_metadata
            }
        
        # Use the special collection ID for text extraction jobs
        
        # Create background job for text extraction
        job_data = JobCreate(
            user_id=effective_user_id,
            collection_id=TEXT_EXTRACTION_COLLECTION_ID,
            job_type=job_type,
            title=input_data["title"],
            description=input_data["description"],
            processing_options=processing_options,
            input_data=input_data
        )
        
        job = await job_service.create_job(job_data, effective_user_id)
        started = await job_service.start_job_processing(job.id)
        
        # No activity logging
        
        return JobSubmissionResponse(
            job_id=job.id,
            status=job.status,
            message="Text extraction job created and started" if started else "Text extraction job created but failed to start",
            estimated_duration_seconds=job.estimated_duration_seconds
        )
        
    except Exception as e:
        logger.error(f"Failed to create text extraction job: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create text extraction job: {str(e)}"
        )
