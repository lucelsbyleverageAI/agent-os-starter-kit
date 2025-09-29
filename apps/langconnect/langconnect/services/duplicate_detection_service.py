"""Duplicate detection service for preventing duplicate document uploads."""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union
from fastapi import UploadFile

from langconnect.database.document import DocumentManager
from langconnect.database.connection import get_db_connection

logger = logging.getLogger(__name__)


@dataclass
class DuplicateCheckResult:
    """Result of duplicate detection check."""
    is_duplicate: bool
    should_overwrite: bool
    action: str  # 'skip', 'overwrite', 'process'
    reason: str
    existing_document: Optional[Dict[str, Any]] = None
    existing_document_id: Optional[str] = None


@dataclass
class FileProcessingDecision:
    """Decision about how to process a file."""
    filename: str
    content_hash: str
    action: str  # 'skip', 'overwrite', 'process'
    reason: str
    file_content: bytes
    existing_document_id: Optional[str] = None
    existing_document: Optional[Dict[str, Any]] = None


@dataclass
class DuplicateDetectionSummary:
    """Summary of duplicate detection results for a batch."""
    files_to_process: List[FileProcessingDecision]
    skipped_files: List[Dict[str, Any]]
    overwritten_files: List[Dict[str, Any]]
    total_files_checked: int
    total_files_to_process: int
    total_files_skipped: int


class DuplicateDetectionService:
    """Service for detecting and handling duplicate documents."""
    
    def __init__(self, document_manager: DocumentManager):
        """Initialize the duplicate detection service.
        
        Args:
            document_manager: DocumentManager instance for the target collection
        """
        self.document_manager = document_manager
    
    @staticmethod
    def calculate_content_hash(content: bytes) -> str:
        """Calculate SHA-256 hash of file content.
        
        Args:
            content: File content as bytes
            
        Returns:
            SHA-256 hash as hexadecimal string
        """
        return hashlib.sha256(content).hexdigest()
    
    async def check_file_duplicate(
        self, 
        filename: str, 
        content_hash: str
    ) -> DuplicateCheckResult:
        """Check if a file is a duplicate based on content hash and filename.
        
        Args:
            filename: Original filename
            content_hash: SHA-256 hash of file content
            
        Returns:
            DuplicateCheckResult with decision and details
        """
        # First check for exact content duplicate (same hash)
        content_duplicate = await self.document_manager.check_duplicate_by_content_hash(content_hash)
        
        if content_duplicate:
            return DuplicateCheckResult(
                is_duplicate=True,
                should_overwrite=False,
                action='skip',
                reason='exact_duplicate',
                existing_document=content_duplicate,
                existing_document_id=content_duplicate['id']
            )
        
        # Check for filename duplicate (same name, potentially different content)
        filename_duplicate = await self.document_manager.check_duplicate_by_filename(filename)
        
        if filename_duplicate:
            existing_hash = filename_duplicate.get('content_hash')
            
            # If existing document has no hash (legacy document), allow overwrite
            if not existing_hash:
                return DuplicateCheckResult(
                    is_duplicate=False,
                    should_overwrite=True,
                    action='overwrite',
                    reason='same_filename_legacy_document',
                    existing_document=filename_duplicate,
                    existing_document_id=filename_duplicate['id']
                )
            
            # If hashes are different, this is an updated version
            if existing_hash != content_hash:
                return DuplicateCheckResult(
                    is_duplicate=False,
                    should_overwrite=True,
                    action='overwrite',
                    reason='same_filename_different_content',
                    existing_document=filename_duplicate,
                    existing_document_id=filename_duplicate['id']
                )
            
            # This shouldn't happen (same filename and hash but not caught by content check)
            # but handle gracefully
            return DuplicateCheckResult(
                is_duplicate=True,
                should_overwrite=False,
                action='skip',
                reason='exact_duplicate_by_filename',
                existing_document=filename_duplicate,
                existing_document_id=filename_duplicate['id']
            )
        
        # No duplicates found, proceed with processing
        return DuplicateCheckResult(
            is_duplicate=False,
            should_overwrite=False,
            action='process',
            reason='new_file'
        )
    
    async def process_file_batch(
        self, 
        files: List[UploadFile]
    ) -> DuplicateDetectionSummary:
        """Process a batch of files for duplicate detection.
        
        Args:
            files: List of uploaded files to check
            
        Returns:
            DuplicateDetectionSummary with processing decisions
        """
        files_to_process = []
        skipped_files = []
        overwritten_files = []
        
        # Track hashes within this batch to detect intra-batch duplicates
        batch_hashes = {}
        
        for file in files:
            try:
                # Read file content and calculate hash
                content = await file.read()
                await file.seek(0)  # Reset file pointer for later use
                
                content_hash = self.calculate_content_hash(content)
                filename = file.filename or "unknown_file"
                
                # Check for duplicates within this batch first
                if content_hash in batch_hashes:
                    skipped_files.append({
                        "filename": filename,
                        "action": "skipped",
                        "reason": "duplicate_in_batch",
                        "duplicate_of": batch_hashes[content_hash]["filename"],
                        "content_hash": content_hash
                    })
                    logger.info(f"Skipped {filename} - duplicate within batch of {batch_hashes[content_hash]['filename']}")
                    continue
                
                # Check against existing documents in collection
                duplicate_result = await self.check_file_duplicate(filename, content_hash)
                
                if duplicate_result.action == 'skip':
                    skipped_files.append({
                        "filename": filename,
                        "action": "skipped",
                        "reason": duplicate_result.reason,
                        "existing_document_id": duplicate_result.existing_document_id,
                        "existing_document": {
                            "title": duplicate_result.existing_document.get("title"),
                            "original_filename": duplicate_result.existing_document.get("original_filename"),
                            "created_at": duplicate_result.existing_document.get("created_at")
                        } if duplicate_result.existing_document else None,
                        "content_hash": content_hash
                    })
                    logger.info(f"Skipped {filename} - {duplicate_result.reason}")
                
                elif duplicate_result.action == 'overwrite':
                    files_to_process.append(FileProcessingDecision(
                        filename=filename,
                        content_hash=content_hash,
                        action='overwrite',
                        reason=duplicate_result.reason,
                        file_content=content,
                        existing_document_id=duplicate_result.existing_document_id,
                        existing_document=duplicate_result.existing_document
                    ))
                    
                    overwritten_files.append({
                        "filename": filename,
                        "action": "overwritten",
                        "reason": duplicate_result.reason,
                        "previous_document_id": duplicate_result.existing_document_id,
                        "previous_document": {
                            "title": duplicate_result.existing_document.get("title"),
                            "original_filename": duplicate_result.existing_document.get("original_filename"),
                            "created_at": duplicate_result.existing_document.get("created_at")
                        } if duplicate_result.existing_document else None,
                        "content_hash": content_hash
                    })
                    logger.info(f"Will overwrite {filename} - {duplicate_result.reason}")
                
                else:  # process
                    files_to_process.append(FileProcessingDecision(
                        filename=filename,
                        content_hash=content_hash,
                        action='process',
                        reason=duplicate_result.reason,
                        file_content=content
                    ))
                    logger.info(f"Will process {filename} - new file")
                
                # Track this file in batch
                batch_hashes[content_hash] = {
                    "filename": filename,
                    "action": duplicate_result.action
                }
                
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                skipped_files.append({
                    "filename": file.filename or "unknown_file",
                    "action": "skipped",
                    "reason": "processing_error",
                    "error_message": str(e)
                })
        
        return DuplicateDetectionSummary(
            files_to_process=files_to_process,
            skipped_files=skipped_files,
            overwritten_files=overwritten_files,
            total_files_checked=len(files),
            total_files_to_process=len(files_to_process),
            total_files_skipped=len(skipped_files)
        )
    
    async def check_text_duplicate(
        self, 
        text_content: str, 
        title: str
    ) -> DuplicateCheckResult:
        """Check if text content is a duplicate.
        
        Args:
            text_content: Text content to check
            title: Title/identifier for the text
            
        Returns:
            DuplicateCheckResult with decision and details
        """
        content_hash = self.calculate_content_hash(text_content.encode('utf-8'))
        
        # Check for exact content duplicate
        content_duplicate = await self.document_manager.check_duplicate_by_content_hash(content_hash)
        
        if content_duplicate:
            return DuplicateCheckResult(
                is_duplicate=True,
                should_overwrite=False,
                action='skip',
                reason='exact_text_duplicate',
                existing_document=content_duplicate,
                existing_document_id=content_duplicate['id']
            )
        
        # For text content, we don't do filename-based overwriting
        # since titles are more flexible than filenames
        return DuplicateCheckResult(
            is_duplicate=False,
            should_overwrite=False,
            action='process',
            reason='new_text_content'
        )
    
    async def check_url_duplicate(
        self, 
        url: str
    ) -> DuplicateCheckResult:
        """Check if URL content is a duplicate.
        
        Note: For URLs, we check by URL itself as stored in metadata,
        not by content hash since content might change over time.
        
        Args:
            url: URL to check
            
        Returns:
            DuplicateCheckResult with decision and details
        """
        # Check for same URL in metadata
        async with get_db_connection() as conn:
            query = """
                SELECT id, collection_id, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE collection_id = $1 AND cmetadata->>'url' = $2
                LIMIT 1
            """
            
            result = await conn.fetchrow(query, self.document_manager.collection_id, url)
            
            if result:
                metadata = json.loads(result["cmetadata"]) if result["cmetadata"] else {}
                existing_document = {
                    "id": str(result["id"]),
                    "collection_id": str(result["collection_id"]),
                    "metadata": metadata,
                    "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                    "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                    "title": metadata.get("title", "Untitled"),
                    "url": metadata.get("url"),
                }
                
                return DuplicateCheckResult(
                    is_duplicate=True,
                    should_overwrite=False,
                    action='skip',
                    reason='same_url_already_processed',
                    existing_document=existing_document,
                    existing_document_id=existing_document['id']
                )
        
        return DuplicateCheckResult(
            is_duplicate=False,
            should_overwrite=False,
            action='process',
            reason='new_url'
        ) 