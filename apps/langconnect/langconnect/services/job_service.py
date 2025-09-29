"""Job service for managing background document processing jobs."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from langconnect.database.connection import get_db_connection
from langconnect.database.collections import Collection
from langconnect.models.job import (
    JobStatus, 
    JobType, 
    JobCreate, 
    JobUpdate, 
    JobResponse, 
    JobListResponse,
    JobSubmissionResponse,
    ProcessingOptions
)
from langconnect.services.enhanced_document_processor import EnhancedDocumentProcessor

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing background job processing."""
    
    def __init__(self):
        """Initialize the job service."""
        self.running_jobs: dict[str, asyncio.Task] = {}
        self.job_queue: asyncio.Queue = asyncio.Queue()
        self.max_concurrent_jobs = 3
        self.queue_processor_task: Optional[asyncio.Task] = None
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="job-worker")
        self.enhanced_processor = EnhancedDocumentProcessor()
        self._start_queue_processor()
    
    def _start_queue_processor(self):
        """Start the background queue processor"""
        if self.queue_processor_task is None or self.queue_processor_task.done():
            self.queue_processor_task = asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Background task to process queued jobs"""
        while True:
            try:
                # Check if we can start more jobs
                if len(self.running_jobs) < self.max_concurrent_jobs:
                    try:
                        # Wait for a job in the queue (with timeout to avoid blocking forever)
                        job_id, runtime_data = await asyncio.wait_for(
                            self.job_queue.get(), timeout=2.0
                        )
                        await self._start_job_immediately(job_id, runtime_data)
                        logger.info(f"Started queued job {job_id} ({len(self.running_jobs)}/{self.max_concurrent_jobs} slots used)")
                    except asyncio.TimeoutError:
                        # No jobs in queue, continue loop
                        pass
                else:
                    # At capacity, wait a bit before checking again
                    await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(5)  # Wait longer on errors
    
    async def create_job(
        self, 
        job_data: JobCreate, 
        user_id: str
    ) -> JobResponse:
        """Create a new processing job.
        
        Args:
            job_data: Job creation data
            user_id: ID of the user creating the job
            
        Returns:
            Created job information
        """
        job_id = str(uuid.uuid4())
        
        # Estimate processing time based on input data
        estimated_time = self._estimate_processing_time(job_data)
        
        async with get_db_connection() as conn:
            # Insert new job record
            query = """
                INSERT INTO processing_jobs (
                    id, user_id, collection_id, job_type, status, title, description,
                    input_data, processing_options
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, user_id, collection_id, job_type, status, title, description,
                         input_data, processing_options, progress_percent, current_step,
                         total_steps, created_at, started_at, completed_at
            """
            
            result = await conn.fetchrow(
                query,
                job_id,
                user_id,
                str(job_data.collection_id),
                job_data.job_type.value,
                JobStatus.PENDING.value,
                job_data.title,
                job_data.description,
                json.dumps(job_data.input_data),
                json.dumps(job_data.processing_options.model_dump()) if job_data.processing_options else None
            )
            
            if not result:
                raise RuntimeError("Failed to create job record")
            
            logger.info(f"Created job {job_id} for user {user_id}")
            
            return JobResponse(
                id=str(result["id"]),
                user_id=result["user_id"],
                collection_id=str(result["collection_id"]),
                job_type=JobType(result["job_type"]),
                status=JobStatus(result["status"]),
                title=result["title"],
                description=result["description"],
                input_data=json.loads(result["input_data"]) if result["input_data"] else {},
                processing_options=ProcessingOptions.model_validate(json.loads(result["processing_options"])) if result["processing_options"] else None,
                progress_percentage=result["progress_percent"] or 0,
                current_step=result["current_step"],
                total_steps=result["total_steps"],
                estimated_duration_seconds=estimated_time,  # Use calculated estimate
                created_at=result["created_at"],
                started_at=result["started_at"],
                completed_at=result["completed_at"]
            )
    
    async def get_job(self, job_id: str, user_id: str, is_service_account: bool = False) -> Optional[JobResponse]:
        """Get job information by ID.
        
        Args:
            job_id: Job identifier
            user_id: ID of the user requesting the job (or service account identity)
            is_service_account: Whether the request is from a service account
            
        Returns:
            Job information or None if not found
        """
        async with get_db_connection() as conn:
            if is_service_account:
                # Service accounts can access all jobs (admin access)
                query = """
                    SELECT id, user_id, collection_id, job_type, status, title, description,
                           input_data, result_data, processing_options, progress_percent, current_step,
                           total_steps, error_message, started_at, completed_at,
                           processing_time_seconds, documents_processed, chunks_created,
                           created_at
                    FROM processing_jobs
                    WHERE id = $1
                """
                result = await conn.fetchrow(query, job_id)
            else:
                # Regular users can only access their own jobs
                query = """
                    SELECT id, user_id, collection_id, job_type, status, title, description,
                           input_data, result_data, processing_options, progress_percent, current_step,
                           total_steps, error_message, started_at, completed_at,
                           processing_time_seconds, documents_processed, chunks_created,
                           created_at
                    FROM processing_jobs
                    WHERE id = $1 AND user_id = $2
                """
                result = await conn.fetchrow(query, job_id, user_id)
            
            if not result:
                return None
            
            # Parse input_data and strip out base64 content for efficiency
            input_data = json.loads(result["input_data"]) if result["input_data"] else {}
            if "files" in input_data and isinstance(input_data["files"], list):
                for file in input_data["files"]:
                    if isinstance(file, dict) and "content_b64" in file:
                        # Remove the base64 content but keep other file metadata
                        file["content_b64"] = "<stripped>"
            
            return JobResponse(
                id=str(result["id"]),
                user_id=result["user_id"],
                collection_id=str(result["collection_id"]),
                job_type=JobType(result["job_type"]),
                status=JobStatus(result["status"]),
                title=result["title"],
                description=result["description"],
                input_data=input_data,
                output_data=json.loads(result["result_data"]) if result["result_data"] else None,
                processing_options=ProcessingOptions.model_validate(json.loads(result["processing_options"])) if result["processing_options"] else None,
                progress_percentage=result["progress_percent"],
                current_step=result["current_step"],
                total_steps=result["total_steps"],
                error_message=result["error_message"],
                started_at=result["started_at"],
                completed_at=result["completed_at"],
                actual_duration_seconds=result["processing_time_seconds"],
                documents_processed=result["documents_processed"],
                chunks_created=result["chunks_created"],
                created_at=result["created_at"]
            )
    
    async def list_jobs(
        self, 
        user_id: str, 
        status_filter: Optional[JobStatus] = None,
        limit: int = 10,
        offset: int = 0,
        is_service_account: bool = False
    ) -> JobListResponse:
        """List jobs for a user.
        
        Args:
            user_id: ID of the user (or service account identity)
            status_filter: Optional status to filter by
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            is_service_account: Whether the request is from a service account
            
        Returns:
            List of jobs with pagination info
        """
        async with get_db_connection() as conn:
            if is_service_account:
                # Service accounts can see all jobs (admin access)
                where_clause = ""
                params = []
                
                if status_filter:
                    where_clause = "WHERE status = $1"
                    params.append(status_filter.value)
                    limit_param = "$2"
                    offset_param = "$3"
                else:
                    limit_param = "$1"
                    offset_param = "$2"
            else:
                # Regular users can only see their own jobs
                where_clause = "WHERE user_id = $1"
                params = [user_id]
                
                if status_filter:
                    where_clause += " AND status = $2"
                    params.append(status_filter.value)
                    limit_param = "$3"
                    offset_param = "$4"
                else:
                    limit_param = "$2"
                    offset_param = "$3"
            
            params.extend([limit, offset])
            
            # Get jobs with pagination
            query = f"""
                SELECT id, user_id, collection_id, job_type, status, title, description,
                       input_data, result_data, processing_options, progress_percent, current_step,
                       total_steps, error_message, started_at, completed_at,
                       processing_time_seconds, documents_processed, chunks_created,
                       created_at
                FROM processing_jobs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit_param} OFFSET {offset_param}
            """
            
            results = await conn.fetch(query, *params)
            
            # Get total count
            if is_service_account:
                if status_filter:
                    count_query = "SELECT COUNT(*) FROM processing_jobs WHERE status = $1"
                    count_params = [status_filter.value]
                else:
                    count_query = "SELECT COUNT(*) FROM processing_jobs"
                    count_params = []
            else:
                if status_filter:
                    count_query = "SELECT COUNT(*) FROM processing_jobs WHERE user_id = $1 AND status = $2"
                    count_params = [user_id, status_filter.value]
                else:
                    count_query = "SELECT COUNT(*) FROM processing_jobs WHERE user_id = $1"
                    count_params = [user_id]
            
            total_count = await conn.fetchval(count_query, *count_params)
            
            jobs = []
            for result in results:
                jobs.append(JobResponse(
                    id=str(result["id"]),
                    user_id=result["user_id"],
                    collection_id=str(result["collection_id"]),
                    job_type=JobType(result["job_type"]),
                    status=JobStatus(result["status"]),
                    title=result["title"],
                    description=result["description"],
                    input_data=json.loads(result["input_data"]) if result["input_data"] else {},
                    output_data=json.loads(result["result_data"]) if result["result_data"] else None,
                    processing_options=ProcessingOptions.model_validate(json.loads(result["processing_options"])) if result["processing_options"] else None,
                    progress_percentage=result["progress_percent"],
                    current_step=result["current_step"],
                    total_steps=result["total_steps"],
                    error_message=result["error_message"],
                    started_at=result["started_at"],
                    completed_at=result["completed_at"],
                    actual_duration_seconds=result["processing_time_seconds"],
                    documents_processed=result["documents_processed"],
                    chunks_created=result["chunks_created"],
                    created_at=result["created_at"]
                ))
            
            return JobListResponse(
                jobs=jobs,
                total=total_count,
                limit=limit,
                offset=offset,
                has_more=offset + len(jobs) < total_count
            )
    
    async def update_job_progress(
        self, 
        job_id: str, 
        update_data: JobUpdate
    ) -> bool:
        """Update job progress and status."""
        try:
            async with get_db_connection() as conn:
                # Build the UPDATE statement dynamically based on provided fields
                set_clauses = []
                params = []
                param_count = 1
                
                if update_data.status is not None:
                    set_clauses.append(f"status = ${param_count}")
                    params.append(update_data.status.value)
                    param_count += 1
                
                if update_data.progress_percentage is not None:
                    set_clauses.append(f"progress_percent = ${param_count}")
                    params.append(update_data.progress_percentage)
                    param_count += 1
                
                if update_data.current_step is not None:
                    set_clauses.append(f"current_step = ${param_count}")
                    params.append(update_data.current_step)
                    param_count += 1
                
                if update_data.total_steps is not None:
                    set_clauses.append(f"total_steps = ${param_count}")
                    params.append(update_data.total_steps)
                    param_count += 1
                
                if update_data.error_message is not None:
                    set_clauses.append(f"error_message = ${param_count}")
                    params.append(update_data.error_message)
                    param_count += 1
                
                if update_data.output_data is not None:
                    set_clauses.append(f"result_data = ${param_count}")
                    params.append(json.dumps(update_data.output_data))
                    param_count += 1
                
                if update_data.documents_processed is not None:
                    set_clauses.append(f"documents_processed = ${param_count}")
                    params.append(update_data.documents_processed)
                    param_count += 1
                
                if update_data.chunks_created is not None:
                    set_clauses.append(f"chunks_created = ${param_count}")
                    params.append(update_data.chunks_created)
                    param_count += 1
                
                # Handle timing fields based on status
                if update_data.status == JobStatus.PROCESSING:
                    set_clauses.append("started_at = COALESCE(started_at, NOW())")
                elif update_data.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    set_clauses.append("completed_at = COALESCE(completed_at, NOW())")
                    set_clauses.append("""
                        processing_time_seconds = CASE 
                            WHEN started_at IS NOT NULL THEN EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER
                            ELSE processing_time_seconds 
                        END
                    """.strip())
                
                if not set_clauses:
                    return True  # Nothing to update
                
                # Build and execute the query
                query = f"""
                    UPDATE processing_jobs 
                    SET {', '.join(set_clauses)}
                    WHERE id = ${param_count}
                """
                params.append(job_id)
                
                result = await conn.execute(query, *params)
                rows_affected = int(result.split()[-1])
                
                return rows_affected > 0
                
        except Exception as e:
            logger.error(f"Failed to update job progress for {job_id}: {e}")
            return False
    
    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        """Cancel a job.
        
        Args:
            job_id: Job identifier
            user_id: ID of the user canceling the job
            
        Returns:
            True if job was cancelled
        """
        # Cancel the running task if it exists
        if job_id in self.running_jobs:
            task = self.running_jobs[job_id]
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled running task for job {job_id}")
        
        # Update job status in database
        async with get_db_connection() as conn:
            query = """
                UPDATE processing_jobs 
                SET status = $1, completed_at = NOW()
                WHERE id = $2 AND user_id = $3 AND status IN ($4, $5)
                RETURNING id
            """
            
            result = await conn.fetchrow(
                query,
                JobStatus.CANCELLED.value,
                job_id,
                user_id,
                JobStatus.PENDING.value,
                JobStatus.PROCESSING.value
            )
            
            if result:
                logger.info(f"Cancelled job {job_id} for user {user_id}")
                return True
            else:
                logger.warning(f"Could not cancel job {job_id} - may not exist or already completed")
                return False
    
    async def start_job_processing(self, job_id: str, runtime_data: dict = None) -> bool:
        """Start processing a job in the background.
        
        Args:
            job_id: Job identifier
            runtime_data: Optional runtime data (like file content) not stored in DB
            
        Returns:
            True if job processing was started or queued
        """
        if job_id in self.running_jobs:
            logger.warning(f"Job {job_id} is already running")
            return False
        
        # Check if we can start immediately
        if len(self.running_jobs) < self.max_concurrent_jobs:
            return await self._start_job_immediately(job_id, runtime_data)
        
        # Queue the job if at capacity
        await self.job_queue.put((job_id, runtime_data))
        
        # Update job status to indicate queuing
        queue_size = self.job_queue.qsize()
        await self.update_job_progress(job_id, JobUpdate(
            status=JobStatus.PENDING,
            current_step=f"Queued (position {queue_size}, {len(self.running_jobs)} jobs running)"
        ))
        
        logger.info(f"Job {job_id} queued (queue size: {queue_size})")
        return True
    
    async def _start_job_immediately(self, job_id: str, runtime_data: dict = None) -> bool:
        """Start job processing immediately"""
        try:
            # Create and start the processing task
            task = asyncio.create_task(self._process_job(job_id, runtime_data))
            self.running_jobs[job_id] = task
            
            # Add callback to clean up completed tasks
            def on_job_complete(completed_task):
                self.running_jobs.pop(job_id, None)
                logger.info(f"Job {job_id} completed, {len(self.running_jobs)} jobs still running")
            
            task.add_done_callback(on_job_complete)
            
            logger.info(f"Started job {job_id} immediately ({len(self.running_jobs)}/{self.max_concurrent_jobs} slots used)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start job {job_id}: {e}")
            return False
    
    def get_queue_status(self) -> dict:
        """Get current queue and processing status"""
        return {
            "running_jobs": len(self.running_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "queued_jobs": self.job_queue.qsize(),
            "running_job_ids": list(self.running_jobs.keys()),
        }
    
    async def _process_job(self, job_id: str, runtime_data: dict = None) -> None:
        """Process a job asynchronously."""
        try:
            # Get job details without user restriction for background processing
            async with get_db_connection() as conn:
                query = """
                    SELECT id, user_id, collection_id, job_type, status, input_data, 
                           processing_options, title, description
                    FROM processing_jobs
                    WHERE id = $1
                """
                result = await conn.fetchrow(query, job_id)
                
            if not result:
                logger.error(f"Job {job_id} not found for processing")
                return
            
            # Convert to JobResponse for processing
            job = JobResponse(
                id=str(result["id"]),
                user_id=result["user_id"],
                collection_id=str(result["collection_id"]),
                job_type=JobType(result["job_type"]),
                status=JobStatus(result["status"]),
                title=result["title"],
                description=result["description"],
                input_data=json.loads(result["input_data"]) if result["input_data"] else {},
                processing_options=ProcessingOptions.model_validate(json.loads(result["processing_options"])) if result["processing_options"] else None,
                progress_percentage=0,
                current_step=None,
                total_steps=None,
                output_data=None,
                error_message=None,
                error_details=None,
                created_at=datetime.now(UTC),
                started_at=None,
                completed_at=None,
                actual_duration_seconds=None,
                documents_processed=0,
                chunks_created=0,
            )
            
            # Update job status to processing
            await self.update_job_progress(job_id, JobUpdate(
                status=JobStatus.PROCESSING,
                progress_percentage=0,
                current_step="Initializing processing"
            ))
            
            # Initialize enhanced document processor
            processor = EnhancedDocumentProcessor()
            
            # Progress callback to update job status
            def progress_callback(message: str):
                # This runs in the background, so we don't await
                import asyncio
                try:
                    asyncio.create_task(self.update_job_progress(job_id, JobUpdate(
                        current_step=message
                    )))
                except Exception as e:
                    logger.warning(f"Failed to update job progress: {e}")
            
            # Process the job input with new document model support
            # Merge runtime_data (like file content) with stored input_data
            processing_input = job.input_data.copy()
            if runtime_data:
                # Merge runtime data (like files with content) into processing input
                for key, value in runtime_data.items():
                    processing_input[key] = value
            
            # --- Branch logic based on job type ---
            if job.job_type == JobType.TEXT_PROCESSING:
                # Handle one-off text extraction for chat
                # This path does not save to a collection
                result = await processor.process_input(
                    processing_input,
                    job.processing_options,
                    progress_callback,
                    collection_id=None,
                    user_id=job.user_id,
                )

                if result.success and result.documents:
                    # For text extraction, we expect one document with the content
                    extracted_content = result.documents[0].page_content
                    output_data = {"content": extracted_content}
                    
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.COMPLETED,
                        progress_percentage=100,
                        current_step="Extraction complete",
                        output_data=output_data
                    ))
                    logger.info(f"Text extraction job {job_id} completed successfully.")
                elif result.success:
                    # Success but no documents means no content was extracted
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.FAILED,
                        progress_percentage=0,
                        current_step="Processing failed",
                        error_message="No content could be extracted from the source."
                    ))
                    logger.error(f"Text extraction job {job_id} failed: No content extracted.")
                else:
                    # Handle processing failure
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.FAILED,
                        error_message=result.error_message or "Unknown processing error"
                    ))
                    logger.error(f"Text extraction job {job_id} failed: {result.error_message}")
                
                return # End processing for this job type

            # --- Default behavior for other job types (e.g., DOCUMENT_PROCESSING) ---
            
            result = await processor.process_input(
                processing_input,
                job.processing_options,
                progress_callback,
                collection_id=str(job.collection_id),
                user_id=job.user_id,
                use_document_model=True  # Always use new model for jobs
            )
            
            if result.success:
                # Update progress
                await self.update_job_progress(job_id, JobUpdate(
                    progress_percentage=80,
                    current_step="Adding documents to collection"
                ))
                
                # Add documents to collection (only if there are documents to add)
                added_ids = []
                if result.documents:
                    collection = Collection(
                        collection_id=str(job.collection_id),
                        user_id=job.user_id,
                    )
                    
                    added_ids = await collection.upsert(result.documents)
                
                # Prepare output data including duplicate detection results
                output_data = {
                    "added_chunk_ids": added_ids,
                    "documents_processed": len(result.documents),
                    "chunks_created": len(added_ids),
                    "processing_metadata": result.metadata
                }
                
                # Add duplicate detection results if available
                if result.duplicate_summary:
                    output_data["duplicate_summary"] = result.duplicate_summary
                    logger.info(f"🔍 Adding duplicate_summary to job output: {result.duplicate_summary}")
                if result.files_skipped:
                    output_data["files_skipped"] = result.files_skipped
                    logger.info(f"🔍 Adding files_skipped to job output: {len(result.files_skipped)} files")
                if result.files_overwritten:
                    output_data["files_overwritten"] = result.files_overwritten
                    logger.info(f"🔍 Adding files_overwritten to job output: {len(result.files_overwritten)} files")
                
                # Complete job
                await self.update_job_progress(job_id, JobUpdate(
                    status=JobStatus.COMPLETED,
                    progress_percentage=100,
                    current_step="Processing completed",
                    output_data=output_data,
                    documents_processed=len(result.documents),
                    chunks_created=len(added_ids)
                ))
                
                # Create appropriate log message
                if result.duplicate_summary:
                    skipped_count = result.duplicate_summary.get("total_files_skipped", 0)
                    overwritten_count = result.duplicate_summary.get("files_overwritten", 0)
                    processed_count = result.duplicate_summary.get("total_files_to_process", 0)
                    logger.info(f"Job {job_id} completed successfully. Processed: {processed_count}, Skipped: {skipped_count}, Overwritten: {overwritten_count}. Added {len(added_ids)} chunks.")
                else:
                    logger.info(f"Job {job_id} completed successfully. Added {len(added_ids)} chunks.")
                
            else:
                # Job failed
                await self.update_job_progress(job_id, JobUpdate(
                    status=JobStatus.FAILED,
                    progress_percentage=0,
                    current_step="Processing failed",
                    error_message=result.error_message
                ))
                
                logger.error(f"Job {job_id} failed: {result.error_message}")
                
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            await self.update_job_progress(job_id, JobUpdate(
                status=JobStatus.FAILED,
                progress_percentage=0,
                current_step="Processing failed",
                error_message=str(e)
            ))
    
    def _estimate_processing_time(self, job_data: JobCreate) -> int:
        """Estimate processing time based on job data.
        
        Args:
            job_data: Job creation data
            
        Returns:
            Estimated duration in seconds
        """
        # Basic estimation logic - will be enhanced with real metrics
        base_time = 30  # Base 30 seconds
        
        if job_data.job_type == JobType.DOCUMENT_PROCESSING:
            # Estimate based on file size or content length
            if job_data.input_data and "file_size" in job_data.input_data:
                file_size_mb = job_data.input_data["file_size"] / (1024 * 1024)
                return base_time + int(file_size_mb * 10)  # 10 seconds per MB
        elif job_data.job_type == JobType.YOUTUBE_PROCESSING:
            # YouTube processing typically takes longer
            return base_time + 60
        elif job_data.job_type == JobType.URL_PROCESSING:
            return base_time + 20
        
        return base_time


# Global job service instance
job_service = JobService() 