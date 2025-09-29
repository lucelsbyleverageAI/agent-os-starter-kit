"""API endpoints for job management."""

import logging
from typing import Annotated, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
 
from langconnect.services.job_service import job_service
from langconnect.models.job import (
    JobCreate,
    JobResponse,
    JobListResponse,
    JobSubmissionResponse,
    JobStatus,
    JobType
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post(
    "",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    job_data: JobCreate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Create and start a new background processing job."""
    try:
        # For service accounts, require owner_id in input_data
        if isinstance(actor, ServiceAccount):
            if not job_data.input_data or not job_data.input_data.get("owner_id"):
                raise HTTPException(
                    status_code=400,
                    detail="Service account must specify 'owner_id' in input_data"
                )
            effective_user_id = job_data.input_data["owner_id"]
        else:
            effective_user_id = actor.identity
        
        # Create the job
        job = await job_service.create_job(job_data, effective_user_id)
        
        # Start job processing
        started = await job_service.start_job_processing(job.id)
        
        
        
        return JobSubmissionResponse(
            job_id=job.id,
            status=job.status,
            message="Job created and processing started" if started else "Job created but failed to start processing",
            estimated_duration_seconds=job.estimated_duration_seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create job: {str(e)}"
        )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    status_filter: Optional[JobStatus] = Query(None, description="Filter jobs by status"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
):
    """List jobs for the authenticated user with optional filtering."""
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        jobs = await job_service.list_jobs(
            user_id=effective_user_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
            is_service_account=is_service_account
        )
        
        # Note: List operations are not logged as activities (only CRUD operations are logged)
        
        return jobs
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list jobs: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get details of a specific job."""
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        job = await job_service.get_job(job_id, effective_user_id, is_service_account=is_service_account)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found or access denied"
            )
        
        # Note: Successful get operations are not logged as activities
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job: {str(e)}"
        )


@router.post("/{job_id}/cancel", response_model=dict[str, bool])
async def cancel_job(
    job_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Cancel a running or pending job."""
    try:
        # For service accounts, we need to handle permission differently
        # For now, use actor identity directly
        effective_user_id = actor.identity
        
        success = await job_service.cancel_job(job_id, effective_user_id)
        
        if success:
            return {"success": True}
        else:
            raise HTTPException(
                status_code=404,
                detail="Job not found, already completed, or access denied"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel job: {str(e)}"
        )


@router.get("/status/summary", response_model=dict[str, dict[str, int]])
async def get_job_status_summary(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get a summary of job statuses by type for the authenticated user."""
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        # Get all jobs for the user
        all_jobs = await job_service.list_jobs(
            user_id=effective_user_id,
            limit=1000,  # Get all jobs for summary
            is_service_account=is_service_account
        )
        
        # Build summary
        summary = {}
        for job in all_jobs.jobs:
            job_type = job.job_type.value
            status = job.status.value
            
            if job_type not in summary:
                summary[job_type] = {}
            
            if status not in summary[job_type]:
                summary[job_type][status] = 0
            
            summary[job_type][status] += 1
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status summary: {str(e)}"
        )


# =====================
# Enhanced Job Management Endpoints
# =====================

class DetailedJobResponse(BaseModel):
    """Detailed job response with processing insights."""
    
    # All fields from JobResponse
    id: str
    user_id: str
    collection_id: str
    job_type: JobType
    status: JobStatus
    title: str
    description: Optional[str] = None
    progress_percentage: int
    current_step: Optional[str] = None
    total_steps: Optional[int] = None
    input_data: Dict[str, Any]
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_time_seconds: Optional[int] = None
    documents_processed: int = 0
    chunks_created: int = 0
    
    # Enhanced fields
    preview_content: Optional[str] = None
    processing_insights: Dict[str, Any] = {}
    estimated_completion_time: Optional[str] = None


class JobResultsResponse(BaseModel):
    """Response model for job results."""
    
    success: bool
    job_id: str
    status: JobStatus
    documents_created: int = 0
    chunks_created: int = 0
    document_ids: list[str] = []
    processing_summary: Dict[str, Any] = {}
    error_message: Optional[str] = None


@router.get("/{job_id}/detailed", response_model=DetailedJobResponse)
async def get_job_detailed(
    job_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get detailed job information with processing insights."""
    
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        job = await job_service.get_job(job_id, effective_user_id, is_service_account=is_service_account)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found or access denied"
            )
        
        # Calculate enhanced fields
        preview_content = None
        processing_insights = {}
        estimated_completion = None
        
        # Add preview content if job is completed
        if job.status == JobStatus.COMPLETED and job.result_data:
            if "processing_metadata" in job.result_data:
                metadata = job.result_data["processing_metadata"]
                processing_insights = {
                    "processing_mode": metadata.get("processing_mode", "unknown"),
                    "source_types": metadata.get("source_types", []),
                    "content_analysis": metadata.get("content_analysis", {}),
                    "performance_stats": {
                        "processing_time": job.processing_time_seconds,
                        "avg_chunk_size": metadata.get("avg_chunk_size"),
                        "chunks_per_document": metadata.get("chunks_per_document"),
                    }
                }
            
            # Get preview of first few chunks if available
            if "preview_chunks" in job.result_data:
                preview_content = job.result_data["preview_chunks"][:500] + "..." if len(job.result_data["preview_chunks"]) > 500 else job.result_data["preview_chunks"]
        
        # Estimate completion time for running jobs
        if job.status == JobStatus.PROCESSING and job.estimated_duration_seconds:
            import datetime
            if job.started_at:
                elapsed = (datetime.datetime.utcnow() - job.started_at).total_seconds()
                remaining = max(0, job.estimated_duration_seconds - elapsed)
                estimated_completion = (datetime.datetime.utcnow() + datetime.timedelta(seconds=remaining)).isoformat()
        
        return DetailedJobResponse(
            id=job.id,
            user_id=job.user_id,
            collection_id=str(job.collection_id),
            job_type=job.job_type,
            status=job.status,
            title=job.title,
            description=job.description,
            progress_percentage=job.progress_percentage,
            current_step=job.current_step,
            total_steps=job.total_steps,
            input_data=job.input_data,
            result_data=job.result_data,
            error_message=job.error_message,
            error_details=job.error_details,
            created_at=job.created_at.isoformat() if job.created_at else "",
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            processing_time_seconds=job.processing_time_seconds,
            documents_processed=job.documents_processed,
            chunks_created=job.chunks_created,
            preview_content=preview_content,
            processing_insights=processing_insights,
            estimated_completion_time=estimated_completion,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get detailed job information: {str(e)}"
        )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(
    job_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get processed results from a completed job."""
    
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        job = await job_service.get_job(job_id, effective_user_id, is_service_account=is_service_account)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found or access denied"
            )
        
        # Prepare results response
        if job.status == JobStatus.COMPLETED:
            document_ids = []
            processing_summary = {}
            
            if job.result_data:
                document_ids = job.result_data.get("added_chunk_ids", [])
                processing_summary = {
                    "documents_processed": job.result_data.get("documents_processed", 0),
                    "chunks_created": job.result_data.get("chunks_created", 0),
                    "processing_time": job.processing_time_seconds,
                    "processing_metadata": job.result_data.get("processing_metadata", {}),
                }
            
            return JobResultsResponse(
                success=True,
                job_id=job_id,
                status=job.status,
                documents_created=job.documents_processed,
                chunks_created=job.chunks_created,
                document_ids=document_ids,
                processing_summary=processing_summary,
            )
        
        elif job.status == JobStatus.FAILED:
            return JobResultsResponse(
                success=False,
                job_id=job_id,
                status=job.status,
                error_message=job.error_message,
                processing_summary={
                    "processing_time": job.processing_time_seconds,
                    "error_details": job.error_details or {},
                }
            )
        
        else:
            # Job is still pending or processing
            return JobResultsResponse(
                success=False,
                job_id=job_id,
                status=job.status,
                error_message=f"Job is {job.status.value}, results not available yet",
                processing_summary={
                    "progress_percentage": job.progress_percentage,
                    "current_step": job.current_step,
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job results: {str(e)}"
        )


@router.get("/queue/status", response_model=dict[str, Any])
async def get_queue_status(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get current job queue status"""
    try:
        status = job_service.get_queue_status()
        return {
            "queue_status": status,
            "message": f"{status['running_jobs']} jobs running, {status['queued_jobs']} queued"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get queue status: {str(e)}"
        )


@router.get("/user/summary", response_model=dict[str, Any])
async def get_user_job_summary(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    days: int = Query(default=7, ge=1, le=90, description="Number of days to include in summary"),
):
    """Get comprehensive job statistics and trends for the user."""
    
    try:
        # Detect if this is a service account
        is_service_account = isinstance(actor, ServiceAccount)
        effective_user_id = actor.identity
        
        # Get recent jobs for analysis
        recent_jobs = await job_service.list_jobs(
            user_id=effective_user_id,
            limit=100,  # Get more jobs for better statistics
            is_service_account=is_service_account
        )
        
        # Filter jobs by date range
        import datetime
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        filtered_jobs = [
            job for job in recent_jobs.jobs 
            if job.created_at and job.created_at >= cutoff_date
        ]
        
        # Calculate statistics
        total_jobs = len(filtered_jobs)
        completed_jobs = len([j for j in filtered_jobs if j.status == JobStatus.COMPLETED])
        failed_jobs = len([j for j in filtered_jobs if j.status == JobStatus.FAILED])
        processing_jobs = len([j for j in filtered_jobs if j.status == JobStatus.PROCESSING])
        pending_jobs = len([j for j in filtered_jobs if j.status == JobStatus.PENDING])
        
        # Calculate processing statistics
        completed_processing_times = [
            j.processing_time_seconds for j in filtered_jobs 
            if j.status == JobStatus.COMPLETED and j.processing_time_seconds
        ]
        
        avg_processing_time = (
            sum(completed_processing_times) / len(completed_processing_times) 
            if completed_processing_times else 0
        )
        
        total_documents_processed = sum(j.documents_processed for j in filtered_jobs)
        total_chunks_created = sum(j.chunks_created for j in filtered_jobs)
        
        # Job type breakdown
        job_type_stats = {}
        for job in filtered_jobs:
            job_type = job.job_type.value
            if job_type not in job_type_stats:
                job_type_stats[job_type] = {"total": 0, "completed": 0, "failed": 0}
            
            job_type_stats[job_type]["total"] += 1
            if job.status == JobStatus.COMPLETED:
                job_type_stats[job_type]["completed"] += 1
            elif job.status == JobStatus.FAILED:
                job_type_stats[job_type]["failed"] += 1
        
        return {
            "period_days": days,
            "summary": {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "processing_jobs": processing_jobs,
                "pending_jobs": pending_jobs,
                "success_rate": completed_jobs / total_jobs if total_jobs > 0 else 0,
            },
            "processing_stats": {
                "total_documents_processed": total_documents_processed,
                "total_chunks_created": total_chunks_created,
                "average_processing_time_seconds": int(avg_processing_time),
                "total_processing_time_seconds": sum(completed_processing_times),
            },
            "job_type_breakdown": job_type_stats,
            "recent_activity": [
                {
                    "job_id": job.id,
                    "title": job.title,
                    "status": job.status.value,
                    "job_type": job.job_type.value,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "chunks_created": job.chunks_created,
                }
                for job in sorted(filtered_jobs, key=lambda x: x.created_at or datetime.datetime.min, reverse=True)[:10]
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get user job summary: {str(e)}"
        ) 