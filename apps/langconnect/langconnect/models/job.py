"""Job processing models for background document processing."""

import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status enumeration."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enumeration."""
    
    DOCUMENT_PROCESSING = "document_processing"
    YOUTUBE_PROCESSING = "youtube_processing"
    URL_PROCESSING = "url_processing"
    TEXT_PROCESSING = "text_processing"
    REPROCESS_DOCUMENT = "reprocess_document"


class ProcessingOptions(BaseModel):
    """Processing options for document processing jobs."""
    
    processing_mode: str = Field(
        default="balanced", 
        description="Processing mode: 'fast' (standard processing with table extraction, no OCR), 'balanced' (OCR processing for scanned documents with table extraction)"
    )
    image_processing: str = Field(default="placeholders", description="Image processing method")
    chunking_strategy: str = Field(default="markdown_aware", description="Text chunking strategy")
    ocr_enabled: bool = Field(default=True, description="Enable OCR for scanned documents")
    extract_tables: bool = Field(default=True, description="Extract tables from documents")
    extract_figures: bool = Field(default=True, description="Extract figures from documents")
    language: Optional[str] = Field(default=None, description="Document language for processing")


class JobCreate(BaseModel):
    """Schema for creating a new processing job."""
    
    user_id: str = Field(..., description="ID of the user creating the job")
    collection_id: UUID = Field(..., description="ID of the collection to add documents to")
    job_type: JobType = Field(..., description="Type of processing job")
    title: str = Field(..., description="Human-readable title for the job")
    description: Optional[str] = Field(None, description="Optional description of the job")
    processing_options: ProcessingOptions = Field(default_factory=ProcessingOptions, description="Processing configuration")
    input_data: dict[str, Any] = Field(..., description="Input data for processing (files, URLs, text)")


class JobUpdate(BaseModel):
    """Schema for updating job progress."""
    
    status: Optional[JobStatus] = Field(None, description="New job status")
    progress_percentage: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage", alias="progress_percent")
    current_step: Optional[str] = Field(None, description="Current processing step")
    total_steps: Optional[int] = Field(None, description="Total processing steps")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Optional[dict[str, Any]] = Field(None, description="Detailed error information")
    output_data: Optional[dict[str, Any]] = Field(None, description="Processing results", alias="result_data")
    documents_processed: Optional[int] = Field(None, ge=0, description="Number of documents processed")
    chunks_created: Optional[int] = Field(None, ge=0, description="Number of chunks created")

    class Config:
        populate_by_name = True


class JobResponse(BaseModel):
    """Schema for job response data."""
    
    id: str = Field(..., description="Job ID")
    user_id: str = Field(..., description="User ID who created the job")
    collection_id: str = Field(..., description="Collection ID")
    job_type: JobType = Field(..., description="Type of processing job")
    status: JobStatus = Field(..., description="Current job status")
    
    # Job metadata
    title: str = Field(..., description="Job title")
    description: Optional[str] = Field(None, description="Job description")
    processing_options: Optional[ProcessingOptions] = Field(None, description="Processing configuration")
    
    # Progress tracking
    progress_percentage: int = Field(..., ge=0, le=100, description="Progress percentage", alias="progress_percent")
    current_step: Optional[str] = Field(None, description="Current processing step")
    total_steps: Optional[int] = Field(None, description="Total processing steps")
    
    # Input and results
    input_data: dict[str, Any] = Field(..., description="Input data")
    output_data: Optional[dict[str, Any]] = Field(None, description="Processing results", alias="result_data")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Optional[dict[str, Any]] = Field(None, description="Detailed error information")
    
    # Timing
    created_at: datetime.datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime.datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime.datetime] = Field(None, description="Job completion timestamp")
    
    # Processing stats
    estimated_duration_seconds: Optional[int] = Field(None, description="Estimated duration in seconds")
    actual_duration_seconds: Optional[int] = Field(None, description="Actual processing time in seconds", alias="processing_time_seconds")
    documents_processed: int = Field(default=0, description="Number of documents processed")
    chunks_created: int = Field(default=0, description="Number of chunks created")

    class Config:
        from_attributes = True
        populate_by_name = True


class JobListResponse(BaseModel):
    """Schema for listing jobs with pagination."""
    
    jobs: list[JobResponse] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total number of jobs")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")
    has_more: bool = Field(..., description="Whether there are more pages")


class JobSubmissionResponse(BaseModel):
    """Schema for job submission response."""
    
    job_id: str = Field(..., description="ID of the created job")
    status: JobStatus = Field(..., description="Initial job status")
    message: str = Field(..., description="Human-readable status message")
    estimated_duration_seconds: Optional[int] = Field(None, description="Estimated processing time in seconds")
    # Duplicate detection results
    duplicate_summary: Optional[dict[str, Any]] = Field(None, description="Summary of duplicate detection results")
    files_skipped: Optional[list[dict[str, Any]]] = Field(None, description="Files that were skipped as duplicates")
    files_overwritten: Optional[list[dict[str, Any]]] = Field(None, description="Files that will overwrite existing documents") 