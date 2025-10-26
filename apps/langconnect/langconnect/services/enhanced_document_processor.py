"""Enhanced document processor service that orchestrates all document processing components."""

import logging
import tempfile
import os
import base64
import asyncio
import psutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from fastapi import UploadFile
from langchain_core.documents import Document
from docling.datamodel.base_models import ConversionStatus

from langconnect.models.job import ProcessingOptions, JobType
from langconnect.services.docling_converter_service import DoclingConverterService
from docling.datamodel.base_models import ConversionStatus
from langconnect.services.youtube_service import YouTubeService, YouTubeProcessingError
from langconnect.services.enhanced_chunking_service import EnhancedChunkingService
from langconnect.services.duplicate_detection_service import DuplicateDetectionService
from langconnect.services.excel_processor import excel_processor_service
from langconnect.database.document import DocumentManager

import mimetypes
import csv
import io

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Container for document processing results."""
    documents: List[Document]
    metadata: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    document_records: Optional[List[Dict[str, Any]]] = None  # Full document records for new model
    # Duplicate detection results
    duplicate_summary: Optional[Dict[str, Any]] = None
    files_skipped: Optional[List[Dict[str, Any]]] = None
    files_overwritten: Optional[List[Dict[str, Any]]] = None


class EnhancedDocumentProcessor:
    """Main enhanced document processor that orchestrates all processing components."""
    
    def __init__(self):
        """Initialize the enhanced document processor."""
        self.docling_service = DoclingConverterService()
        self.youtube_service = YouTubeService()
        self.chunking_service = EnhancedChunkingService()
        
        # Resource management for parallel processing
        self.max_concurrent_files = min(3, max(1, psutil.cpu_count() // 2))
        self.max_memory_usage_mb = 1024  # 1GB limit per job
        self.thread_pool = ThreadPoolExecutor(max_workers=2)  # For CPU-bound operations
    
    def _get_available_memory_mb(self) -> int:
        """Get available system memory in MB"""
        try:
            memory = psutil.virtual_memory()
            return int(memory.available / (1024 * 1024))
        except:
            return 1024  # Default assumption
    
    def _get_memory_usage_mb(self) -> int:
        """Get current process memory usage in MB"""
        try:
            process = psutil.Process()
            return int(process.memory_info().rss / (1024 * 1024))
        except:
            return 0
    
    def _estimate_file_size(self, file_obj) -> int:
        """Estimate file size for memory planning"""
        if hasattr(file_obj, 'size') and file_obj.size:
            return file_obj.size
        elif hasattr(file_obj, 'content_b64'):
            # Base64 content, estimate size
            return len(file_obj['content_b64']) * 3 // 4  # Base64 overhead
        else:
            return 1024 * 1024  # 1MB default estimate
    
    def _detect_file_format(self, filename: str, content_type: Optional[str] = None) -> str:
        """Detect file format based on filename and content type.

        Args:
            filename: Name of the file
            content_type: MIME type if available

        Returns:
            Format category: 'simple_text', 'excel_spreadsheet', 'complex_document', 'image', or 'unsupported'
        """
        # Get file extension
        _, ext = os.path.splitext(filename.lower())

        # Simple text formats that don't need Docling
        simple_text_extensions = {'.txt', '.md', '.csv', '.tsv'}
        simple_text_mimes = {'text/plain', 'text/markdown', 'text/csv', 'text/tab-separated-values'}

        # Excel spreadsheet formats (need special handling for calculated values)
        excel_extensions = {'.xlsx', '.xls'}
        excel_mimes = {
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel'
        }

        # Complex document formats that need Docling
        complex_doc_extensions = {'.pdf', '.docx', '.doc', '.pptx', '.ppt', '.html', '.htm'}
        complex_doc_mimes = {
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.ms-powerpoint',
            'text/html'
        }

        # Image formats (need vision analysis and storage)
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif'}
        image_mimes = {
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'image/bmp',
            'image/tiff'
        }

        # Check by extension first
        if ext in simple_text_extensions:
            return 'simple_text'
        elif ext in excel_extensions:
            return 'excel_spreadsheet'
        elif ext in complex_doc_extensions:
            return 'complex_document'
        elif ext in image_extensions:
            return 'image'

        # Check by MIME type if available
        if content_type:
            if content_type in simple_text_mimes:
                return 'simple_text'
            elif content_type in excel_mimes:
                return 'excel_spreadsheet'
            elif content_type in complex_doc_mimes:
                return 'complex_document'
            elif content_type in image_mimes or content_type.startswith('image/'):
                return 'image'

        # Try to guess MIME type from filename
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type:
            if guessed_type in simple_text_mimes:
                return 'simple_text'
            elif guessed_type in excel_mimes:
                return 'excel_spreadsheet'
            elif guessed_type in complex_doc_mimes:
                return 'complex_document'
            elif guessed_type in image_mimes or guessed_type.startswith('image/'):
                return 'image'

        # Default to unsupported for unknown formats
        return 'unsupported'
    
    async def _process_simple_text_file(
        self,
        file_obj: Union[Dict[str, Any], UploadFile],
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None
    ) -> Dict[str, Any]:
        """Process simple text files (.txt, .md, .csv) without Docling.
        
        Args:
            file_obj: File object to process
            processing_options: Processing configuration
            document_manager: Optional document manager
            
        Returns:
            Dictionary with processing results
        """
        # Get filename and content type
        filename = getattr(file_obj, 'filename', 'unknown')
        content_type = getattr(file_obj, 'content_type', None)
        if isinstance(file_obj, dict):
            filename = file_obj.get('filename', 'unknown')
            content_type = file_obj.get('content_type', None)
        
        logger.info(f"Processing simple text file: {filename}")
        
        try:
            # Read file content
            content_bytes = None
            if hasattr(file_obj, 'content'):
                # SimpleUploadFile object
                content_bytes = file_obj.content
            elif hasattr(file_obj, 'read'):
                # UploadFile object
                await file_obj.seek(0)
                content_bytes = await file_obj.read()
            elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                # Base64 content
                content_bytes = base64.b64decode(file_obj['content_b64'])
            else:
                raise ValueError(f"Unknown file object type for {filename}")
            
            # Decode content to text
            try:
                # Try UTF-8 first
                text_content = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    # Fallback to latin-1
                    text_content = content_bytes.decode('latin-1')
                    logger.warning(f"File {filename} decoded using latin-1 fallback")
                except UnicodeDecodeError:
                    # Last resort - ignore errors
                    text_content = content_bytes.decode('utf-8', errors='ignore')
                    logger.warning(f"File {filename} decoded with errors ignored")
            
            # Generate individual document metadata
            individual_title, individual_description = await self._generate_individual_document_metadata(
                filename=filename,
                content=text_content,
                use_ai_metadata=processing_options.use_ai_metadata,
                processing_mode=processing_options.processing_mode
            )
            
            # Determine file format for specific processing
            _, ext = os.path.splitext(filename.lower())
            
            # Process based on file type
            if ext == '.csv':
                # Handle CSV files - can optionally parse structure
                documents = await self._process_csv_content(
                    text_content, filename, individual_title, individual_description
                )
            elif ext == '.md':
                # Handle Markdown files - preserve structure
                documents = await self._process_markdown_content(
                    text_content, filename, individual_title, individual_description
                )
            else:
                # Handle plain text files (.txt and others)
                documents = await self._process_plain_text_content(
                    text_content, filename, individual_title, individual_description
                )
            
            logger.info(f"Created {len(documents)} LangChain documents for {filename}")
            
            # Store full document if using new model
            document_records = []
            document_id = None
            if document_manager and documents:
                # Store the full document content before chunking
                full_content = documents[0].page_content  # First document contains full content
                document_metadata = documents[0].metadata.copy()
                
                # Add content hash to metadata for future duplicate detection
                content_hash = DuplicateDetectionService.calculate_content_hash(content_bytes)
                document_metadata["content_hash"] = content_hash
                
                try:
                    document_id = await document_manager.create_document(
                        content=full_content,
                        metadata=document_metadata
                    )
                    document_records.append({
                        "id": document_id,
                        "content": full_content,
                        "metadata": document_metadata,
                        "filename": filename
                    })
                    logger.info(f"Created document record {document_id} for {filename}")
                except Exception as e:
                    logger.error(f"Failed to create document record for {filename}: {e}")
                    # Continue processing even if document creation fails
            
            # Chunk documents
            if processing_options.chunking_strategy != "none":
                logger.info(f"Chunking documents for {filename} with strategy: {processing_options.chunking_strategy}")
                documents = await self.chunking_service.chunk_documents(
                    documents,
                    processing_options.chunking_strategy
                )
                logger.info(f"After chunking {filename}: {len(documents)} chunks")
            
            # Link chunks to document if using new model
            if document_id:
                for doc in documents:
                    doc.metadata["document_id"] = document_id
            
            logger.info(f"Successfully processed simple text file {filename}")
            
            return {
                "documents": documents,
                "document_records": document_records
            }
            
        except Exception as e:
            logger.error(f"Error processing simple text file {filename}: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _process_csv_content(
        self, 
        content: str, 
        filename: str, 
        title: str, 
        description: str
    ) -> List[Document]:
        """Process CSV content into documents.
        
        Args:
            content: CSV file content as string
            filename: Original filename
            title: Document title
            description: Document description
            
        Returns:
            List of Document objects
        """
        try:
            # Parse CSV to understand structure
            csv_reader = csv.reader(io.StringIO(content))
            rows = list(csv_reader)
            
            if not rows:
                # Empty CSV
                formatted_content = "Empty CSV file"
            else:
                # Format CSV as readable text
                header = rows[0] if rows else []
                data_rows = rows[1:] if len(rows) > 1 else []
                
                formatted_lines = [f"CSV File: {filename}"]
                if header:
                    formatted_lines.append(f"Columns: {', '.join(header)}")
                    formatted_lines.append(f"Rows: {len(data_rows)}")
                    formatted_lines.append("")
                    
                    # Add sample of data (first few rows)
                    sample_size = min(10, len(data_rows))
                    if sample_size > 0:
                        formatted_lines.append("Sample data:")
                        for i, row in enumerate(data_rows[:sample_size]):
                            row_data = []
                            for j, cell in enumerate(row):
                                col_name = header[j] if j < len(header) else f"Column_{j+1}"
                                row_data.append(f"{col_name}: {cell}")
                            formatted_lines.append(f"Row {i+1}: {', '.join(row_data)}")
                        
                        if len(data_rows) > sample_size:
                            formatted_lines.append(f"... and {len(data_rows) - sample_size} more rows")
                
                formatted_content = "\n".join(formatted_lines)
            
            # Create document with metadata
            metadata = {
                "source": filename,
                "source_type": "csv",
                "title": title,
                "description": description,
                "file_type": "text/csv",
                "total_rows": len(rows) if rows else 0,
                "total_columns": len(rows[0]) if rows else 0
            }
            
            document = Document(
                page_content=formatted_content,
                metadata=metadata
            )
            
            return [document]
            
        except Exception as e:
            logger.warning(f"Failed to parse CSV {filename}, treating as plain text: {e}")
            # Fallback to plain text processing
            return await self._process_plain_text_content(content, filename, title, description)
    
    async def _process_markdown_content(
        self, 
        content: str, 
        filename: str, 
        title: str, 
        description: str
    ) -> List[Document]:
        """Process Markdown content into documents.
        
        Args:
            content: Markdown file content as string
            filename: Original filename
            title: Document title
            description: Document description
            
        Returns:
            List of Document objects
        """
        # Create document with metadata optimized for markdown
        metadata = {
            "source": filename,
            "source_type": "markdown",
            "title": title,
            "description": description,
            "file_type": "text/markdown",
            "content_length": len(content),
            "word_count": len(content.split())
        }
        
        document = Document(
            page_content=content,
            metadata=metadata
        )
        
        return [document]
    
    async def _process_plain_text_content(
        self, 
        content: str, 
        filename: str, 
        title: str, 
        description: str
    ) -> List[Document]:
        """Process plain text content into documents.
        
        Args:
            content: Text file content as string
            filename: Original filename
            title: Document title
            description: Document description
            
        Returns:
            List of Document objects
        """
        # Create document with metadata
        metadata = {
            "source": filename,
            "source_type": "text",
            "title": title,
            "description": description,
            "file_type": "text/plain",
            "content_length": len(content),
            "word_count": len(content.split()),
            "line_count": len(content.splitlines())
        }
        
        document = Document(
            page_content=content,
            metadata=metadata
        )
        
        return [document]
    
    async def _process_files_parallel(
        self,
        files: List[Union[Dict[str, Any], UploadFile]],
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process multiple files concurrently with resource management.
        
        Args:
            files: List of files to process
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            document_manager: Optional document manager for new document model
            
        Returns:
            ProcessingResult with processed documents
        """
        # Create semaphore to limit concurrent file processing
        semaphore = asyncio.Semaphore(self.max_concurrent_files)
        
        # Track progress
        completed_files = 0
        total_files = len(files)
        all_documents = []
        all_document_records = []
        processing_errors = []
        
        # Duplicate detection results
        duplicate_summary = None
        files_skipped = []
        files_overwritten = []
        
        async def process_single_file_with_semaphore(file_obj, file_index):
            async with semaphore:
                try:
                    # Update progress
                    filename = getattr(file_obj, 'filename', f'file_{file_index}')
                    if progress_callback:
                        progress_callback(f"Processing file {file_index + 1}/{total_files}: {filename}")
                    
                    # Monitor memory usage before processing
                    memory_before = self._get_memory_usage_mb()
                    if memory_before > self.max_memory_usage_mb * 0.8:  # 80% threshold
                        logger.warning(f"High memory usage ({memory_before}MB), waiting for cleanup")
                        await asyncio.sleep(2)  # Brief pause for GC
                    
                    # Process the file
                    result = await self._process_single_file(
                        file_obj, processing_options, document_manager
                    )
                    
                    # Memory cleanup after processing
                    memory_after = self._get_memory_usage_mb()
                    logger.debug(f"File {file_index + 1} processed: {memory_before}MB -> {memory_after}MB")
                    
                    return result
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_index + 1}: {e}")
                    return {"error": str(e), "file_index": file_index}
        
        # Create tasks for all files
        tasks = [
            process_single_file_with_semaphore(file_obj, i) 
            for i, file_obj in enumerate(files)
        ]
        
        # Process files with progress tracking
        try:
            # Use asyncio.as_completed for real-time progress updates
            for completed_task in asyncio.as_completed(tasks):
                try:
                    result = await completed_task
                    completed_files += 1
                    
                    if "error" in result:
                        processing_errors.append(result["error"])
                    else:
                        if result.get("documents"):
                            all_documents.extend(result["documents"])
                        if result.get("document_records"):
                            all_document_records.extend(result["document_records"])
                        if result.get("duplicate_info"):
                            # Handle duplicate detection results from individual files
                            if not duplicate_summary:
                                duplicate_summary = {
                                    "total_files_checked": 0,
                                    "total_files_to_process": total_files,
                                    "total_files_skipped": 0,
                                    "files_overwritten": 0
                                }
                            
                            dup_info = result["duplicate_info"]
                            if dup_info.get("skipped"):
                                files_skipped.append(dup_info)
                                duplicate_summary["total_files_skipped"] += 1
                            elif dup_info.get("overwritten"):
                                files_overwritten.append(dup_info)
                                duplicate_summary["files_overwritten"] += 1
                            
                            duplicate_summary["total_files_checked"] += 1
                    
                    # Update overall progress
                    progress_percent = int((completed_files / total_files) * 100)
                    if progress_callback:
                        progress_callback(f"Completed {completed_files}/{total_files} files ({progress_percent}%)")
                    
                except Exception as e:
                    processing_errors.append(str(e))
                    completed_files += 1
            
            # Final result compilation
            success = len(processing_errors) == 0 or len(all_documents) > 0
            error_message = "; ".join(processing_errors) if processing_errors else None
            
            # Prepare metadata
            metadata = {
                "files_processed": completed_files - len(processing_errors),
                "total_files": total_files,
                "total_documents": len(all_documents),
                "processing_mode": processing_options.processing_mode,
                "chunking_strategy": processing_options.chunking_strategy,
                "parallel_processing": True,
                "errors": processing_errors if processing_errors else None
            }
            
            # Add duplicate detection summary to metadata
            if duplicate_summary:
                metadata.update(duplicate_summary)
            
            return ProcessingResult(
                documents=all_documents,
                metadata=metadata,
                success=success,
                error_message=error_message,
                document_records=all_document_records if all_document_records else None,
                duplicate_summary=duplicate_summary,
                files_skipped=files_skipped,
                files_overwritten=files_overwritten
            )
            
        except Exception as e:
            logger.error(f"Parallel processing failed: {e}")
            return ProcessingResult(
                documents=[],
                metadata={"processing_mode": processing_options.processing_mode},
                success=False,
                error_message=f"Parallel processing failed: {str(e)}"
            )
    
    async def _process_single_file(
        self,
        file_obj: Union[Dict[str, Any], UploadFile],
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None
    ) -> Dict[str, Any]:
        """Process a single file and return results.
        
        Args:
            file_obj: File object to process
            processing_options: Processing configuration
            document_manager: Optional document manager
            
        Returns:
            Dictionary with processing results
        """
        # Get filename and content type
        filename = getattr(file_obj, 'filename', 'unknown')
        content_type = getattr(file_obj, 'content_type', None)
        if isinstance(file_obj, dict):
            filename = file_obj.get('filename', 'unknown')
            content_type = file_obj.get('content_type', None)
        
        logger.info(f"Processing single file: {filename}")
        
        try:
            # Note: Duplicate detection is handled at the batch level, not per individual file
            
            # Detect file format to determine processing path
            file_format = self._detect_file_format(filename, content_type)
            logger.info(f"Detected format for {filename}: {file_format}")
            
            # Route to appropriate processor
            if file_format == 'simple_text':
                # Process simple text files without Docling
                return await self._process_simple_text_file(
                    file_obj, processing_options, document_manager
                )
            elif file_format == 'excel_spreadsheet':
                # Process Excel files with custom processor for calculated values
                return await self._process_excel_file(
                    file_obj, processing_options, document_manager
                )
            elif file_format == 'complex_document':
                # Process complex documents with Docling
                return await self._process_complex_document_file(
                    file_obj, processing_options, document_manager
                )
            elif file_format == 'image':
                # Process images with vision analysis and storage
                return await self._process_image_file(
                    file_obj, processing_options, document_manager
                )
            else:
                # Unsupported format
                logger.warning(f"Unsupported file format for {filename}: {file_format}")
                return {"error": f"Unsupported file format: {filename}. Please convert to a supported format."}
                
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _process_excel_file(
        self,
        file_obj: Union[Dict[str, Any], UploadFile],
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None
    ) -> Dict[str, Any]:
        """Process Excel files with calculated value extraction.

        Args:
            file_obj: File object to process
            processing_options: Processing configuration
            document_manager: Optional document manager

        Returns:
            Dictionary with processing results
        """
        # Get filename
        filename = getattr(file_obj, 'filename', 'unknown')
        if isinstance(file_obj, dict):
            filename = file_obj.get('filename', 'unknown')

        logger.info(f"Processing Excel file: {filename}")

        try:
            # Convert to temporary file for processing
            temp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{filename}') as temp_file:
                    temp_file_path = temp_file.name

                    # Write file content to temp file
                    if hasattr(file_obj, 'content'):
                        # SimpleUploadFile object
                        temp_file.write(file_obj.content)
                    elif hasattr(file_obj, 'read'):
                        # UploadFile object
                        await file_obj.seek(0)
                        content = await file_obj.read()
                        temp_file.write(content)
                    elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                        # Base64 content
                        content = base64.b64decode(file_obj['content_b64'])
                        temp_file.write(content)
                    else:
                        raise ValueError(f"Unknown file object type for {filename}")

                    temp_file.flush()

                logger.info(f"Created temporary Excel file: {temp_file_path}")

                # Process with Excel processor
                documents = await excel_processor_service.process_excel_to_documents(
                    temp_file_path,
                    filename,
                    ""  # Description will be generated if needed
                )

                # Generate individual document metadata if requested
                if documents and processing_options.use_ai_metadata:
                    full_content = documents[0].page_content
                    individual_title, individual_description = await self._generate_individual_document_metadata(
                        filename=filename,
                        content=full_content,
                        use_ai_metadata=True,
                        processing_mode=processing_options.processing_mode
                    )

                    # Update metadata
                    for doc in documents:
                        doc.metadata["title"] = individual_title
                        doc.metadata["description"] = individual_description

                logger.info(f"Created {len(documents)} LangChain documents for Excel file {filename}")

                # Store full document if using new model
                document_records = []
                document_id = None
                if document_manager and documents:
                    # Store the full document content before chunking
                    full_content = documents[0].page_content
                    document_metadata = documents[0].metadata.copy()

                    # Add content hash to metadata for future duplicate detection
                    if hasattr(file_obj, 'content'):
                        content_for_hash = file_obj.content
                    elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                        content_for_hash = base64.b64decode(file_obj['content_b64'])
                    else:
                        content_for_hash = full_content.encode('utf-8')

                    content_hash = DuplicateDetectionService.calculate_content_hash(content_for_hash)
                    document_metadata["content_hash"] = content_hash

                    try:
                        document_id = await document_manager.create_document(
                            content=full_content,
                            metadata=document_metadata
                        )
                        document_records.append({
                            "id": document_id,
                            "content": full_content,
                            "metadata": document_metadata,
                            "filename": filename
                        })
                        logger.info(f"Created document record {document_id} for Excel file {filename}")
                    except Exception as e:
                        logger.error(f"Failed to create document record for Excel file {filename}: {e}")
                        # Continue processing even if document creation fails

                # Chunk documents
                if processing_options.chunking_strategy != "none":
                    logger.info(f"Chunking Excel documents for {filename} with strategy: {processing_options.chunking_strategy}")
                    documents = await self.chunking_service.chunk_documents(
                        documents,
                        processing_options.chunking_strategy
                    )
                    logger.info(f"After chunking {filename}: {len(documents)} chunks")

                # Link chunks to document if using new model
                if document_id:
                    for doc in documents:
                        doc.metadata["document_id"] = document_id

                logger.info(f"Successfully processed Excel file {filename}")

                return {
                    "documents": documents,
                    "document_records": document_records
                }

            finally:
                # Clean up temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.debug(f"Cleaned up temporary Excel file: {temp_file_path}")
                    except OSError as cleanup_error:
                        logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")

        except Exception as e:
            logger.error(f"Error processing Excel file {filename}: {e}", exc_info=True)
            return {"error": str(e)}

    async def _process_image_file(
        self,
        file_obj: Union[Dict[str, Any], UploadFile],
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None
    ) -> Dict[str, Any]:
        """Process image files with AI vision analysis and storage.

        Args:
            file_obj: File object to process
            processing_options: Processing configuration
            document_manager: Optional document manager

        Returns:
            Dictionary with processing results
        """
        from langconnect.services.storage_service import storage_service
        from langconnect.services.vision_analysis_service import vision_analysis_service

        # Get filename and content type
        filename = getattr(file_obj, 'filename', 'unknown')
        content_type = getattr(file_obj, 'content_type', 'image/jpeg')
        if isinstance(file_obj, dict):
            filename = file_obj.get('filename', 'unknown')
            content_type = file_obj.get('content_type', 'image/jpeg')

        logger.info(f"Processing image file: {filename}")

        try:
            # Read image content
            image_bytes = None
            if hasattr(file_obj, 'content'):
                # SimpleUploadFile object
                image_bytes = file_obj.content
            elif hasattr(file_obj, 'read'):
                # UploadFile object
                await file_obj.seek(0)
                image_bytes = await file_obj.read()
            elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                # Base64 content
                image_bytes = base64.b64decode(file_obj['content_b64'])
            else:
                raise ValueError(f"Unknown file object type for {filename}")

            # Determine image format from content type or filename
            image_format = 'jpeg'  # default
            if content_type:
                if 'png' in content_type:
                    image_format = 'png'
                elif 'webp' in content_type:
                    image_format = 'webp'
                elif 'gif' in content_type:
                    image_format = 'gif'
            else:
                # Try from extension
                ext = os.path.splitext(filename.lower())[1]
                if ext in {'.png'}:
                    image_format = 'png'
                elif ext in {'.webp'}:
                    image_format = 'webp'
                elif ext in {'.gif'}:
                    image_format = 'gif'

            # Always use AI vision analysis for images
            logger.info(f"Analyzing image {filename} with AI vision")
            vision_metadata = await vision_analysis_service.analyze_image(
                image_data=image_bytes,
                image_format=image_format,
                fallback_title=os.path.splitext(filename)[0]
            )

            # Extract the three fields
            title = vision_metadata.title
            short_description = vision_metadata.short_description
            detailed_description = vision_metadata.detailed_description

            logger.info(
                f"Vision analysis complete - Title: '{title}', "
                f"Short: '{short_description[:50]}...', "
                f"Detailed: {len(detailed_description)} chars"
            )

            # Upload image to storage (only if document_manager exists)
            storage_info = None
            if document_manager:
                collection_id = document_manager.collection_id

                logger.info(f"Uploading image to storage for collection {collection_id}")
                storage_info = await storage_service.upload_image(
                    file_data=image_bytes,
                    filename=filename,
                    content_type=content_type,
                    collection_uuid=collection_id
                )
                logger.info(f"Image uploaded to: {storage_info['storage_path']}")
            else:
                logger.warning("No document_manager provided - image will not be uploaded to storage")

            # Create document metadata
            document_metadata = {
                "source": filename,
                "title": title,
                "description": short_description,
                "file_type": "image",
                "content_type": content_type,
                "image_format": image_format,
            }

            # Add storage information if available
            if storage_info:
                document_metadata["storage_path"] = storage_info["storage_path"]
                document_metadata["storage_bucket"] = storage_info["bucket"]
                document_metadata["storage_file_path"] = storage_info["file_path"]

            # Add content hash for duplicate detection
            content_hash = DuplicateDetectionService.calculate_content_hash(image_bytes)
            document_metadata["content_hash"] = content_hash

            # Create LangChain document with detailed description as content
            # This is what will be chunked and searched
            document = Document(
                page_content=detailed_description,
                metadata=document_metadata
            )

            documents = [document]
            logger.info(f"Created LangChain document for image {filename}")

            # Store full document if using new model
            document_records = []
            document_id = None
            if document_manager:
                # Store the document with detailed description as content
                document_id = await document_manager.create_document(
                    content=detailed_description,
                    metadata=document_metadata
                )

                document_records.append({
                    "id": document_id,
                    "title": title,
                    "description": short_description,
                    "content": detailed_description,
                    "metadata": document_metadata
                })

                logger.info(f"Created document record {document_id} for image {filename}")

            # Chunk the detailed description
            if processing_options.chunking_strategy:
                logger.info(f"Chunking image description with strategy: {processing_options.chunking_strategy}")
                documents = await self.chunking_service.chunk_documents(
                    documents=documents,
                    chunking_strategy=processing_options.chunking_strategy
                )
                logger.info(f"After chunking {filename}: {len(documents)} chunks")

            # Link chunks to document if using new model
            if document_id:
                for doc in documents:
                    doc.metadata["document_id"] = document_id

            logger.info(f"Successfully processed image file {filename}")

            return {
                "documents": documents,
                "document_records": document_records
            }

        except Exception as e:
            logger.error(f"Error processing image file {filename}: {e}", exc_info=True)
            return {"error": str(e)}

    async def _process_complex_document_file(
        self,
        file_obj: Union[Dict[str, Any], UploadFile],
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None
    ) -> Dict[str, Any]:
        """Process complex document files using Docling.

        Args:
            file_obj: File object to process
            processing_options: Processing configuration
            document_manager: Optional document manager

        Returns:
            Dictionary with processing results
        """
        import time

        # Get filename and file info
        filename = getattr(file_obj, 'filename', 'unknown')
        if isinstance(file_obj, dict):
            filename = file_obj.get('filename', 'unknown')

        logger.info(f"{'='*80}")
        logger.info(f"📄 Processing complex document file: {filename}")
        logger.info(f"⚙️  Processing mode: {processing_options.processing_mode}")
        logger.info(f"⚙️  Chunking strategy: {processing_options.chunking_strategy}")

        processing_start_time = time.time()
        
        try:
            # Convert to temporary file for processing
            temp_file_path = None
            try:
                logger.info("📦 Creating temporary file for Docling processing...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{filename}') as temp_file:
                    temp_file_path = temp_file.name

                    # Write file content to temp file
                    if hasattr(file_obj, 'content'):
                        # SimpleUploadFile object
                        content_bytes = file_obj.content
                        temp_file.write(content_bytes)
                        logger.info(f"📝 Wrote {len(content_bytes)} bytes from SimpleUploadFile")
                    elif hasattr(file_obj, 'read'):
                        # UploadFile object
                        await file_obj.seek(0)
                        content_bytes = await file_obj.read()
                        temp_file.write(content_bytes)
                        logger.info(f"📝 Wrote {len(content_bytes)} bytes from UploadFile")
                    elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                        # Base64 content
                        content_bytes = base64.b64decode(file_obj['content_b64'])
                        temp_file.write(content_bytes)
                        logger.info(f"📝 Wrote {len(content_bytes)} bytes from base64 content")
                    else:
                        raise ValueError(f"Unknown file object type for {filename}")

                    temp_file.flush()

                file_size_mb = os.path.getsize(temp_file_path) / (1024 * 1024)
                logger.info(f"✅ Created temporary file: {temp_file_path} ({file_size_mb:.2f} MB)")
                
                # Process with Docling
                logger.info("🚀 Starting Docling document conversion...")
                docling_start_time = time.time()

                conversion_result = await self.docling_service.convert_document(
                    temp_file_path,
                    processing_options
                )

                docling_elapsed = time.time() - docling_start_time
                logger.info(f"⏱️  Docling conversion completed in {docling_elapsed:.2f}s")
                logger.info(f"📊 Conversion status: {conversion_result.status}")
                
                if conversion_result.status == ConversionStatus.SUCCESS:
                    # Get page count for logging
                    page_count = len(conversion_result.document.pages) if conversion_result.document else 0
                    logger.info(f"✅ SUCCESS: Extracted {page_count} pages from {filename}")

                    # Convert to LangChain documents first
                    logger.info("📝 Converting Docling result to LangChain documents...")
                    documents = self._convert_docling_result_to_documents(
                        conversion_result,
                        filename,
                        filename,  # Temporary title, will be updated
                        ""  # Temporary description, will be updated
                    )

                    # Get full content for metadata generation
                    full_content = documents[0].page_content if documents else ""
                    content_length = len(full_content)
                    logger.info(f"📄 Extracted {content_length} characters of content")

                    # Generate individual document metadata (with AI if requested)
                    if processing_options.use_ai_metadata:
                        logger.info("🤖 Generating AI metadata (title & description)...")
                    else:
                        logger.info("📋 Using filename-based metadata...")

                    individual_title, individual_description = await self._generate_individual_document_metadata(
                        filename=filename,
                        content=full_content,
                        use_ai_metadata=processing_options.use_ai_metadata,
                        processing_mode=processing_options.processing_mode
                    )

                    logger.info(f"📌 Title: {individual_title}")
                    if individual_description:
                        logger.info(f"📌 Description: {individual_description[:100]}...")

                    # Update the document metadata with generated title and description
                    for doc in documents:
                        doc.metadata["title"] = individual_title
                        doc.metadata["description"] = individual_description

                    logger.info(f"✅ Created {len(documents)} LangChain document(s) for {filename}")

                    # Store full document if using new model
                    document_records = []
                    document_id = None
                    if document_manager and documents:
                        # Store the full document content before chunking
                        full_content = documents[0].page_content  # First document contains full content
                        document_metadata = documents[0].metadata.copy()

                        # Add content hash to metadata for future duplicate detection
                        if hasattr(file_obj, 'content'):
                            content_for_hash = file_obj.content
                        elif isinstance(file_obj, dict) and 'content_b64' in file_obj:
                            content_for_hash = base64.b64decode(file_obj['content_b64'])
                        else:
                            content_for_hash = full_content.encode('utf-8')

                        content_hash = DuplicateDetectionService.calculate_content_hash(content_for_hash)
                        document_metadata["content_hash"] = content_hash

                        try:
                            document_id = await document_manager.create_document(
                                content=full_content,
                                metadata=document_metadata
                            )
                            document_records.append({
                                "id": document_id,
                                "content": full_content,
                                "metadata": document_metadata,
                                "filename": filename
                            })
                            logger.info(f"Created document record {document_id} for {filename}")
                        except Exception as e:
                            logger.error(f"Failed to create document record for {filename}: {e}")
                            # Continue processing even if document creation fails

                    # Chunk documents
                    if processing_options.chunking_strategy != "none":
                        logger.info(f"✂️  Chunking documents with strategy: {processing_options.chunking_strategy}")
                        chunking_start = time.time()

                        documents = await self.chunking_service.chunk_documents(
                            documents,
                            processing_options.chunking_strategy
                        )

                        chunking_elapsed = time.time() - chunking_start
                        logger.info(f"✅ Chunking completed in {chunking_elapsed:.2f}s: {len(documents)} chunks created")
                    else:
                        logger.info("⏭️  Skipping chunking (strategy: none)")

                    # Link chunks to document if using new model
                    if document_id:
                        logger.info(f"🔗 Linking {len(documents)} chunks to document {document_id}")
                        for doc in documents:
                            doc.metadata["document_id"] = document_id

                    total_elapsed = time.time() - processing_start_time
                    logger.info(f"{'='*80}")
                    logger.info(f"✅ COMPLETE: Successfully processed {filename} in {total_elapsed:.2f}s")
                    logger.info(f"📊 Final stats: {len(documents)} chunks, {page_count} pages, {content_length} chars")
                    logger.info(f"{'='*80}")

                    return {
                        "documents": documents,
                        "document_records": document_records
                    }

                else:
                    total_elapsed = time.time() - processing_start_time
                    logger.error(f"{'='*80}")
                    logger.error(f"❌ FAILED: Conversion failed for {filename} after {total_elapsed:.2f}s")
                    logger.error(f"📊 Status: {conversion_result.status}")
                    logger.error(f"{'='*80}")
                    return {"error": f"Conversion failed with status: {conversion_result.status}"}

            finally:
                # Clean up temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.debug(f"🗑️  Cleaned up temporary file: {temp_file_path}")
                    except OSError as cleanup_error:
                        logger.warning(f"⚠️  Failed to cleanup temp file {temp_file_path}: {cleanup_error}")

        except Exception as e:
            total_elapsed = time.time() - processing_start_time
            logger.error(f"{'='*80}")
            logger.error(f"❌ ERROR: Exception while processing {filename} after {total_elapsed:.2f}s")
            logger.error(f"📊 Error: {str(e)}")
            logger.error(f"{'='*80}")
            logger.error(f"Full traceback:", exc_info=True)
            return {"error": str(e)}
        
    async def process_input(
        self,
        input_data: Dict[str, Any],
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        use_document_model: bool = True
    ) -> ProcessingResult:
        """Process input data based on type and options.
        
        Args:
            input_data: Input data containing files, URLs, or text
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            collection_id: Collection ID for document model (required if use_document_model=True)
            user_id: User ID for document model (required if use_document_model=True)
            use_document_model: Whether to use the new document table model
            
        Returns:
            ProcessingResult with documents and metadata
        """
        try:
            if progress_callback:
                progress_callback("Analyzing input data")
            
            # Initialize document manager if using new model
            document_manager = None
            if use_document_model and collection_id and user_id:
                document_manager = DocumentManager(collection_id, user_id)
                logger.info(f"🔍 Created DocumentManager for collection {collection_id}, user {user_id}")
            else:
                logger.info(f"🔍 No DocumentManager created: use_document_model={use_document_model}, collection_id={collection_id}, user_id={user_id}")
            
            # Determine processing type and route accordingly
            if "batch_items" in input_data:
                return await self._process_batch_items(
                    input_data["batch_items"],
                    input_data.get("title", "Batch Processing"),
                    input_data.get("description", ""),
                    processing_options,
                    progress_callback,
                    document_manager
                )
            elif "files" in input_data:
                return await self._process_files(
                    input_data["files"], 
                    input_data.get("title", ""),
                    input_data.get("description", ""),
                    processing_options, 
                    progress_callback,
                    document_manager
                )
            elif "urls" in input_data:
                return await self._process_urls(
                    input_data["urls"],
                    input_data.get("title", ""),
                    input_data.get("description", ""),
                    processing_options,
                    progress_callback,
                    document_manager
                )
            elif "url" in input_data:
                # Handle single URL case
                return await self._process_urls(
                    [input_data["url"]],
                    input_data.get("title", ""),
                    input_data.get("description", ""),
                    processing_options,
                    progress_callback,
                    document_manager
                )
            elif "text_content" in input_data:
                return await self._process_text(
                    input_data["text_content"],
                    input_data.get("title", ""),
                    input_data.get("description", ""),
                    processing_options,
                    progress_callback,
                    document_manager
                )
            else:
                return ProcessingResult(
                    documents=[],
                    metadata={},
                    success=False,
                    error_message="No valid input data provided. Expected 'batch_items', 'files', 'urls', 'url', or 'text_content'"
                )
                
        except Exception as e:
            logger.error(f"Error in process_input: {e}")
            return ProcessingResult(
                documents=[],
                metadata={"error_details": str(e)},
                success=False,
                error_message=f"Processing failed: {str(e)}"
            )
    
    async def _process_files(
        self,
        files: List[Union[Dict[str, Any], UploadFile]],
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process files using intelligent parallel/sequential processing with duplicate detection.
        
        Args:
            files: List of file dictionaries with 'filename', 'content_b64', and 'content_type' OR UploadFile objects
            title: Document title (used for job-level tracking)
            description: Document description (used for job-level tracking)
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            document_manager: Optional document manager for new document model
            
        Returns:
            ProcessingResult with processed documents and duplicate detection results
        """
        try:
            if progress_callback:
                progress_callback(f"Preparing to process {len(files)} file(s)")
            
            logger.info(f"Starting enhanced file processing for {len(files)} files")
            
            # Convert dictionary files to UploadFile-like objects
            upload_files = []
            for file_info in files:
                if hasattr(file_info, 'filename'):
                    # Already an UploadFile object
                    upload_files.append(file_info)
                else:
                    # Create a temporary UploadFile-like object from dictionary
                    from io import BytesIO
                    import base64
                    
                    filename = file_info['filename']
                    content_b64 = file_info.get('content_b64', file_info.get('content'))
                    
                    if isinstance(content_b64, str):
                        content = base64.b64decode(content_b64)
                    else:
                        content = content_b64
                    
                    # Create a simple file-like object
                    class SimpleUploadFile:
                        def __init__(self, filename: str, content: bytes):
                            self.filename = filename
                            self.content = content
                            self._position = 0
                        
                        async def read(self):
                            return self.content
                        
                        async def seek(self, position: int):
                            self._position = position
                    
                    upload_files.append(SimpleUploadFile(filename, content))
            
            # Determine processing strategy based on resource constraints and file characteristics
            available_memory = self._get_available_memory_mb()
            total_size = sum(self._estimate_file_size(f) for f in upload_files)
            total_size_mb = total_size // (1024 * 1024)
            
            # Decision logic for parallel vs sequential processing
            should_process_parallel = (
                len(upload_files) > 1 and 
                len(upload_files) <= self.max_concurrent_files and
                total_size_mb < self.max_memory_usage_mb and
                available_memory > 500  # Require at least 500MB available
            )
            
            if should_process_parallel:
                logger.info(f"🚀 Using parallel processing for {len(upload_files)} files (estimated {total_size_mb}MB)")
                if progress_callback:
                    progress_callback(f"Using parallel processing for optimal performance")
                return await self._process_files_parallel(
                    upload_files, processing_options, progress_callback, document_manager
                )
            else:
                logger.info(f"📝 Using sequential processing for {len(upload_files)} files (size limit or resource constraints)")
                if progress_callback:
                    progress_callback(f"Using sequential processing for resource management")
                return await self._process_files_sequential(
                    upload_files, processing_options, progress_callback, document_manager
                )
        
        except Exception as e:
            logger.error(f"🚨 File processing failed: {e}", exc_info=True)
            return ProcessingResult(
                documents=[],
                metadata={"processing_mode": processing_options.processing_mode},
                success=False,
                error_message=str(e)
            )
    
    async def _process_files_sequential(
        self,
        upload_files: List[Union[Dict[str, Any], UploadFile]],
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process files sequentially (legacy logic with duplicate detection).
        
        This is the fallback method when parallel processing is not suitable.
        """
        # Perform duplicate detection if document manager is available
        duplicate_summary = None
        files_skipped = []
        files_overwritten = []
        files_to_process = upload_files  # Default: process all files
        
        if document_manager:
            try:
                if progress_callback:
                    progress_callback(f"Checking {len(upload_files)} file(s) for duplicates")
                
                logger.info(f"🔍 Initializing duplicate detection service for {len(upload_files)} files")
                duplicate_service = DuplicateDetectionService(document_manager)
                detection_result = await duplicate_service.process_file_batch(upload_files)
                logger.info(f"🔍 Duplicate detection result: {detection_result.total_files_skipped} skipped, {detection_result.total_files_to_process} to process")
            except Exception as e:
                logger.error(f"🚨 Duplicate detection failed: {e}")
                # Fall back to processing all files without duplicate detection
                detection_result = None
            
            if detection_result:
                duplicate_summary = {
                    "total_files_checked": detection_result.total_files_checked,
                    "total_files_to_process": detection_result.total_files_to_process,
                    "total_files_skipped": detection_result.total_files_skipped,
                    "files_overwritten": len(detection_result.overwritten_files)
                }
                
                files_skipped = detection_result.skipped_files
                files_overwritten = detection_result.overwritten_files
                
                # Only process files that weren't skipped
                files_to_process = []
                for decision in detection_result.files_to_process:
                    # Find the original file object
                    for orig_file in upload_files:
                        if orig_file.filename == decision.filename:
                            files_to_process.append(orig_file)
                            break
                
                if progress_callback:
                    skipped_count = len(files_skipped)
                    overwritten_count = len(files_overwritten)
                    if skipped_count > 0 or overwritten_count > 0:
                        progress_callback(f"Duplicate check complete: {skipped_count} skipped, {overwritten_count} to overwrite, {len(files_to_process)} to process")
                
                logger.info(f"Duplicate detection complete: {len(files_to_process)} files to process, {len(files_skipped)} skipped")
                
                # Handle document deletions for overwrite cases
                for decision in detection_result.files_to_process:
                    if decision.action == 'overwrite' and decision.existing_document_id:
                        try:
                            await document_manager.delete_document(decision.existing_document_id)
                            logger.info(f"Deleted existing document {decision.existing_document_id} for overwrite of {decision.filename}")
                        except Exception as e:
                            logger.warning(f"Failed to delete existing document {decision.existing_document_id}: {e}")
            else:
                logger.warning("🚨 Duplicate detection failed, processing all files without duplicate checking")
        
        # Process files sequentially
        all_documents = []
        document_records = []
        files_processed = 0
        
        for i, file_obj in enumerate(files_to_process):
            try:
                result = await self._process_single_file(
                    file_obj, processing_options, document_manager
                )
                
                if "error" not in result:
                    if result.get("documents"):
                        all_documents.extend(result["documents"])
                    if result.get("document_records"):
                        document_records.extend(result["document_records"])
                    files_processed += 1
                
                # Update progress
                if progress_callback:
                    progress_callback(f"Processed {i+1}/{len(files_to_process)} files")
                    
            except Exception as e:
                logger.error(f"Error processing file {getattr(file_obj, 'filename', 'unknown')}: {e}")
                # Continue with other files
        
        # Prepare final metadata
        metadata = {
            "files_processed": files_processed,
            "total_files": len(upload_files),
            "total_documents": len(all_documents),
            "processing_mode": processing_options.processing_mode,
            "chunking_strategy": processing_options.chunking_strategy,
            "parallel_processing": False,
            "sequential_processing": True
        }
        
        # Add duplicate detection summary to metadata
        if duplicate_summary:
            metadata.update(duplicate_summary)
        
        return ProcessingResult(
            documents=all_documents,
            metadata=metadata,
            success=len(all_documents) > 0 or len(files_skipped) > 0,
            error_message=None,
            document_records=document_records if document_records else None,
            duplicate_summary=duplicate_summary,
            files_skipped=files_skipped,
            files_overwritten=files_overwritten
        )
    
    async def _process_urls(
        self,
        urls: List[str],
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process URLs (including YouTube URLs).
        
        Args:
            urls: List of URLs to process
            title: User-provided title
            description: User-provided description
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            document_manager: Optional document manager for new document model
            
        Returns:
            ProcessingResult
        """
        all_documents = []
        document_records = []
        processing_metadata = {
            "processing_mode": processing_options.processing_mode,
            "urls_processed": 0,
            "urls_failed": 0,
            "failed_urls": [],
            "total_urls": len(urls),
            "youtube_urls": 0,
            "web_urls": 0
        }
        
        for i, url in enumerate(urls):
            try:
                if progress_callback:
                    progress_callback(f"Processing URL {i+1}/{len(urls)}: {url}")
                
                # Check if it's a YouTube URL
                if self.youtube_service.is_youtube_url(url):
                    processing_metadata["youtube_urls"] += 1
                    # Process YouTube URL (initially with temporary title)
                    documents = await self.youtube_service.process_youtube_url(
                        url, "", "", progress_callback  # Empty title/description for now
                    )

                    # Generate AI metadata if requested and we have documents
                    if documents and processing_options.use_ai_metadata:
                        full_content = documents[0].page_content if documents else ""

                        # Generate individual metadata for YouTube video
                        individual_title, individual_description = await self._generate_individual_document_metadata(
                            filename=url,
                            content=full_content,
                            use_ai_metadata=True,
                            processing_mode=processing_options.processing_mode
                        )

                        # Update the document metadata with AI-generated title and description
                        for doc in documents:
                            doc.metadata["title"] = individual_title
                            doc.metadata["description"] = individual_description
                    elif documents and title:
                        # Use user-provided title if no AI metadata
                        for doc in documents:
                            doc.metadata["title"] = title
                            doc.metadata["description"] = description or ""
                    elif documents:
                        # Fallback: Use video ID as title
                        video_id = documents[0].metadata.get('video_id', 'unknown')
                        for doc in documents:
                            doc.metadata["title"] = title or f"YouTube Video {video_id}"
                            doc.metadata["description"] = description or ""
                else:
                    processing_metadata["web_urls"] += 1
                    # Process regular URL with Docling
                    conversion_result = await self.docling_service.convert_url(
                        url,
                        processing_options,
                        progress_callback
                    )

                    if conversion_result.status == ConversionStatus.SUCCESS:
                        # Convert to documents first to get content
                        documents = self._convert_docling_result_to_documents(
                            conversion_result,
                            url,
                            url,  # Temporary title, will be updated
                            ""  # Temporary description, will be updated
                        )

                        # Get full content for metadata generation
                        full_content = documents[0].page_content if documents else ""

                        # Generate individual metadata for URL (with AI if requested)
                        individual_title, individual_description = await self._generate_individual_document_metadata(
                            filename=url,
                            content=full_content,
                            use_ai_metadata=processing_options.use_ai_metadata,
                            processing_mode=processing_options.processing_mode
                        )

                        # Update the document metadata with generated title and description
                        for doc in documents:
                            doc.metadata["title"] = individual_title
                            doc.metadata["description"] = individual_description
                    else:
                        logger.warning(f"Failed to convert URL {url}: {conversion_result.status}")
                        continue
                
                # Store full document if using new model
                document_id = None
                if document_manager and documents:
                    # Store the full document content before chunking
                    full_content = documents[0].page_content  # First document contains full content
                    document_metadata = documents[0].metadata.copy()
                    
                    try:
                        document_id = await document_manager.create_document(
                            content=full_content,
                            metadata=document_metadata
                        )
                        document_records.append({
                            "id": document_id,
                            "content": full_content,
                            "metadata": document_metadata,
                            "url": url
                        })
                        logger.info(f"Created document record {document_id} for URL {url}")
                    except Exception as e:
                        logger.error(f"Failed to create document record for URL {url}: {e}")
                        # Continue processing even if document creation fails
                
                # Chunk the documents if we have any
                if documents and processing_options.chunking_strategy != "none":
                    if progress_callback:
                        progress_callback(f"Chunking documents from URL {url}")
                    
                    documents = await self.chunking_service.chunk_documents(
                        documents,
                        processing_options.chunking_strategy,
                        progress_callback=progress_callback
                    )
                
                # Link chunks to document if using new model
                if document_id:
                    for doc in documents:
                        doc.metadata["document_id"] = document_id
                
                all_documents.extend(documents)
                processing_metadata["urls_processed"] += 1
                
            except YouTubeProcessingError as e:
                logger.error(f"YouTube processing error for {url}: {e}")
                processing_metadata["urls_failed"] += 1
                processing_metadata["failed_urls"].append({
                    "url": url,
                    "error": str(e),
                    "type": "youtube"
                })
            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                processing_metadata["urls_failed"] += 1
                processing_metadata["failed_urls"].append({
                    "url": url,
                    "error": str(e),
                    "type": "web"
                })
        
        # Optimize chunks for retrieval
        if all_documents:
            optimized_chunks = self.chunking_service.optimize_chunks_for_retrieval(all_documents)
            
            # Add chunking stats
            chunking_stats = self.chunking_service.get_chunking_stats(optimized_chunks)
            processing_metadata.update(chunking_stats)
            
            return ProcessingResult(
                documents=optimized_chunks,
                metadata=processing_metadata,
                success=processing_metadata["urls_processed"] > 0,
                document_records=document_records if document_records else None
            )
        else:
            return ProcessingResult(
                documents=[],
                metadata=processing_metadata,
                success=False,
                error_message="No documents could be processed from the provided URLs"
            )
    
    async def _process_text(
        self,
        text_content: str,
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process raw text content.
        
        Args:
            text_content: Raw text to process
            title: User-provided title
            description: User-provided description
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            document_manager: Optional document manager for new document model
            
        Returns:
            ProcessingResult
        """
        if progress_callback:
            progress_callback("Processing text content")

        # Generate metadata (with AI if requested and no user-provided title)
        if processing_options.use_ai_metadata and not title:
            # Use AI to generate title and description
            individual_title, individual_description = await self._generate_individual_document_metadata(
                filename="Text Input",
                content=text_content,
                use_ai_metadata=True,
                processing_mode=processing_options.processing_mode
            )
        else:
            # Use user-provided or fallback values
            individual_title = title or "Text Input"
            individual_description = description or ""

        # Create document from text
        metadata = {
            "source_type": "text",
            "title": individual_title,
            "description": individual_description,
            "processing_mode": processing_options.processing_mode,
            "content_length": len(text_content),
            "word_count": len(text_content.split())
        }

        document = Document(
            page_content=text_content,
            metadata=metadata
        )
        
        # Store full document if using new model
        document_records = []
        document_id = None
        if document_manager:
            try:
                document_id = await document_manager.create_document(
                    content=text_content,
                    metadata=metadata
                )
                document_records.append({
                    "id": document_id,
                    "content": text_content,
                    "metadata": metadata,
                    "source": "text_input"
                })
                logger.info(f"Created document record {document_id} for text input")
            except Exception as e:
                logger.error(f"Failed to create document record for text input: {e}")
                # Continue processing even if document creation fails
        
        # Chunk the document
        if progress_callback:
            progress_callback("Chunking text content")
        
        chunked_documents = await self.chunking_service.chunk_documents(
            [document],
            processing_options.chunking_strategy,
            progress_callback=progress_callback
        )
        
        # Link chunks to document if using new model
        if document_id:
            for doc in chunked_documents:
                doc.metadata["document_id"] = document_id
        
        # Optimize chunks for retrieval
        optimized_chunks = self.chunking_service.optimize_chunks_for_retrieval(chunked_documents)
        
        # Add processing metadata
        processing_metadata = {
            "processing_mode": processing_options.processing_mode,
            "source_type": "text",
            "original_length": len(text_content),
        }
        
        # Add chunking stats
        chunking_stats = self.chunking_service.get_chunking_stats(optimized_chunks)
        processing_metadata.update(chunking_stats)
        
        return ProcessingResult(
            documents=optimized_chunks,
            metadata=processing_metadata,
            success=True,
            document_records=document_records if document_records else None
        )
    
    async def _generate_individual_document_metadata(
        self,
        filename: str,
        content: str = None,
        use_ai_metadata: bool = False,
        processing_mode: str = "balanced"
    ) -> Tuple[str, str]:
        """Generate individual document title and description.

        Args:
            filename: Original filename
            content: Full document content (required for AI generation)
            use_ai_metadata: Whether to use AI to generate metadata
            processing_mode: Processing mode used (not currently used)

        Returns:
            Tuple of (title, description)
        """
        import os

        # Clean up filename for fallback title
        name_without_ext = os.path.splitext(filename)[0]
        clean_title = (name_without_ext
                      .replace('_', ' ')
                      .replace('-', ' ')
                      .replace('.', ' ')
                      .strip())
        fallback_title = ' '.join(word.capitalize() for word in clean_title.split())

        # If AI metadata is requested and content is available
        if use_ai_metadata and content:
            try:
                from langconnect.services.ai_metadata_service import ai_metadata_service

                logger.info(f"Generating AI metadata for {filename}")
                metadata = await ai_metadata_service.generate_metadata(
                    content=content,
                    fallback_name=fallback_title
                )

                return metadata.name, metadata.description

            except Exception as e:
                logger.warning(f"AI metadata generation failed for {filename}: {e}. Using fallback.")
                # Fall through to fallback logic

        # Fallback: Use filename-based title with empty description
        return fallback_title, ""

    def _convert_docling_result_to_documents(
        self,
        conversion_result,
        source_name: str,
        title: str,
        description: str
    ) -> List[Document]:
        """Convert Docling ConversionResult to LangChain Documents.
        
        Args:
            conversion_result: Result from Docling conversion
            source_name: Name of the source (filename or URL)
            title: User-provided title
            description: User-provided description
            
        Returns:
            List of Document objects
        """
        if not conversion_result.document:
            logger.warning(f"No document content in conversion result for {source_name}")
            return []
        
        # Extract content and metadata from Docling result
        content = conversion_result.document.export_to_markdown()
        
        # Get processing metadata from Docling
        docling_metadata = self.docling_service.extract_content_metadata(conversion_result)
        
        # Create comprehensive metadata
        metadata = {
            "source_name": source_name,
            "title": title or source_name,
            "description": description or "",
            "source_type": "file" if not source_name.startswith("http") else "url",
            "processing_approach": "docling_enhanced",
            "content_format": "markdown",
            "content_length": len(content),
            **docling_metadata
        }
        
        # Create single document (will be chunked later)
        document = Document(
            page_content=content,
            metadata=metadata
        )
        
        return [document]
    
    async def _process_batch_items(
        self,
        batch_items: List[Dict[str, Any]],
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process a batch of mixed items (files, URLs, text).
        
        Args:
            batch_items: List of batch items with type and content
            title: Batch title
            description: Batch description
            processing_options: Processing configuration
            progress_callback: Optional progress callback
            
        Returns:
            ProcessingResult with processed documents
        """
        if progress_callback:
            progress_callback(f"Processing batch of {len(batch_items)} items")
        
        all_documents = []
        batch_metadata = {
            "processing_mode": processing_options.processing_mode,
            "total_items": len(batch_items),
            "items_processed": 0,
            "items_failed": 0,
            "failed_items": [],
            "file_items": 0,
            "url_items": 0,
            "youtube_items": 0,
            "text_items": 0
        }
        
        for i, item in enumerate(batch_items):
            try:
                if progress_callback:
                    progress_callback(f"Processing batch item {i+1}/{len(batch_items)}: {item.get('title', 'Untitled')}")

                item_type = item.get("type", "").lower()

                # If AI metadata is enabled, use empty strings to trigger AI generation
                # Otherwise, use provided title or generic "Batch Item N"
                if processing_options.use_ai_metadata:
                    item_title = item.get("title", "")
                    item_description = item.get("description", "")
                else:
                    item_title = item.get("title", f"Batch Item {i+1}")
                    item_description = item.get("description", "")
                
                if item_type == "file":
                    # Handle file items with either direct content or filename reference
                    if "content_b64" in item:
                        # Direct file content provided
                        file_dict = {
                            "filename": item.get("filename", f"batch_file_{i}.bin"),
                            "content_b64": item["content_b64"],
                            "content_type": item.get("content_type", "application/octet-stream"),
                            "size": item.get("size", 0)
                        }
                    elif "filename" in item:
                        # Load file from test directory (for testing purposes)
                        filename = item["filename"]
                        file_path = f"apps/langconnect/tests/test_files/{filename}"
                        if not os.path.exists(file_path):
                            raise ValueError(f"Test file not found: {filename}")
                        
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        
                        # Create file dict for processing
                        file_dict = {
                            "filename": filename,
                            "content_b64": base64.b64encode(content).decode('utf-8'),
                            "content_type": item.get("content_type", "application/octet-stream"),
                            "size": len(content)
                        }
                    else:
                        raise ValueError("File items must specify either 'content_b64' or 'filename'")
                    
                    result = await self._process_files(
                        [file_dict],
                        item_title,
                        item_description,
                        processing_options,
                        progress_callback
                    )
                    batch_metadata["file_items"] += 1
                    
                elif item_type == "url":
                    url = item.get("url")
                    if not url:
                        raise ValueError("URL items must specify 'url'")
                    
                    result = await self._process_urls(
                        [url],
                        item_title,
                        item_description,
                        processing_options,
                        progress_callback
                    )
                    
                    if "youtube.com" in url or "youtu.be" in url:
                        batch_metadata["youtube_items"] += 1
                    else:
                        batch_metadata["url_items"] += 1
                    
                elif item_type == "youtube":
                    url = item.get("url")
                    if not url:
                        raise ValueError("YouTube items must specify 'url'")
                    
                    result = await self._process_urls(
                        [url],
                        item_title,
                        item_description,
                        processing_options,
                        progress_callback
                    )
                    batch_metadata["youtube_items"] += 1
                    
                elif item_type == "text":
                    text_content = item.get("content", item.get("text"))
                    if not text_content:
                        raise ValueError("Text items must specify 'content' or 'text'")
                    
                    result = await self._process_text(
                        text_content,
                        item_title,
                        item_description,
                        processing_options,
                        progress_callback
                    )
                    batch_metadata["text_items"] += 1
                    
                else:
                    raise ValueError(f"Unsupported batch item type: {item_type}. Supported types: file, url, youtube, text")
                
                if result.success:
                    all_documents.extend(result.documents)
                    batch_metadata["items_processed"] += 1
                else:
                    batch_metadata["items_failed"] += 1
                    batch_metadata["failed_items"].append({
                        "item": item,
                        "error": result.error_message
                    })
                    
            except Exception as e:
                logger.error(f"Error processing batch item {i}: {e}")
                batch_metadata["items_failed"] += 1
                batch_metadata["failed_items"].append({
                    "item": item,
                    "error": str(e)
                })
                continue
        
        # Add overall stats
        batch_metadata["total_documents"] = len(all_documents)
        batch_metadata["success_rate"] = batch_metadata["items_processed"] / batch_metadata["total_items"] if batch_metadata["total_items"] > 0 else 0
        
        return ProcessingResult(
            documents=all_documents,
            metadata=batch_metadata,
            success=batch_metadata["items_processed"] > 0,
            error_message=f"Processed {batch_metadata['items_processed']}/{batch_metadata['total_items']} items successfully" if batch_metadata["items_failed"] > 0 else None
        )
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up enhanced document processor")
        self.docling_service.cleanup()
        
        # Clean up thread pool for parallel processing
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True) 