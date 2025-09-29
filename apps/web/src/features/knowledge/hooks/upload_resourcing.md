# Upload Resource Management Analysis & Implementation Plan

## Executive Summary

The current document upload system experiences breakdowns when handling multiple files or concurrent uploads due to architectural limitations around sequential processing, memory management, and lack of concurrency controls. This document outlines the current architecture and proposes a phased implementation plan to address these issues.

## Current Architecture Analysis

### Frontend Layer

#### 1. Upload UI Components
- **File**: `apps/web/src/features/rag/components/enhanced-upload-dialog.tsx`
- **Purpose**: Main upload dialog with tabs for files, URLs, and text
- **Current Behavior**: 
  - Allows unlimited file selection
  - No file count or size validation
  - Processes all content types in single submission

#### 2. File Upload Section
- **File**: `apps/web/src/features/rag/components/file-upload-section.tsx`
- **Purpose**: Handles file selection and validation
- **Current Limitations**:
  - Basic file type validation only
  - No file count limits
  - No total size validation
  - Loads all files into memory for preview

#### 3. Upload Processing Hook
- **File**: `apps/web/src/features/rag/hooks/use-rag.tsx`
- **Function**: `uploadDocumentsEnhanced()` (lines 30-125)
- **Critical Issue**: **Sequential processing of files**
  ```typescript
  // PROBLEM: Each file creates separate HTTP request
  for (const file of uploadData.files) {
    const formData = new FormData();
    formData.append("files", file, file.name);
    // Individual API call per file
    const response = await fetch(url, { method: "POST", body: formData });
  }
  ```
- **Impact**: 10 files = 10 separate API calls + 10 background jobs

#### 4. Job Tracking
- **File**: `apps/web/src/hooks/use-job-tracking.ts`
- **Purpose**: Tracks processing job status and progress
- **Current Issues**:
  - Can become overwhelmed with many concurrent jobs
  - No queuing mechanism for job updates
  - Race conditions possible with rapid job creation

### API Routing Layer

#### 1. Next.js API Proxy
- **File**: `apps/web/src/app/api/langconnect/collections/[collection_id]/documents/route.ts`
- **Purpose**: Proxies requests to backend API
- **Current Behavior**: Direct passthrough to backend

### Backend API Layer

#### 1. Document Upload Endpoint
- **File**: `apps/langconnect/langconnect/api/documents.py`
- **Function**: `upload_documents()` (lines 650-850)
- **Current Behavior**:
  - Accepts multiple files in single request (✅ Good)
  - Creates single background job per request (✅ Good)
  - Converts files to base64 for job storage (⚠️ Memory intensive)

#### 2. Job Management API
- **File**: `apps/langconnect/langconnect/api/jobs.py`
- **Purpose**: Job creation, monitoring, and status updates
- **Current Limitations**:
  - No concurrency limits
  - No job prioritization
  - No resource monitoring

### Background Processing Layer

#### 1. Job Service
- **File**: `apps/langconnect/langconnect/services/job_service.py`
- **Class**: `JobService`
- **Critical Issues**:
  ```python
  # PROBLEM: No concurrency limits
  self.running_jobs: Dict[str, asyncio.Task] = {}
  
  # PROBLEM: Unlimited job creation
  task = asyncio.create_task(self._process_job(job_id, runtime_data))
  self.running_jobs[job_id] = task
  ```
- **Impact**: Can spawn unlimited concurrent processing tasks

#### 2. Document Processor
- **File**: `apps/langconnect/langconnect/services/enhanced_document_processor.py`
- **Function**: `_process_files()` (lines 146-350)
- **Critical Issues**:
  ```python
  # PROBLEM: Sequential file processing within job
  for i, file_obj in enumerate(files_to_process):
    # Each file processed one-by-one
    content = await file_obj.read()  # Loads entire file into memory
    # Docling processing (CPU intensive)
    conversion_result = await self.docling_service.convert_document()
  ```
- **Memory Issues**:
  - Base64 encoding doubles memory usage
  - Temporary files created without guaranteed cleanup
  - No streaming or chunked processing

#### 3. Docling Service Integration
- **File**: `apps/langconnect/langconnect/services/docling_converter_service.py`
- **Purpose**: PDF/document conversion using Docling
- **Limitations**:
  - Synchronous processing (blocks async loop)
  - CPU-intensive OCR operations
  - No parallelization for multiple documents

### Database Layer

#### 1. Document Storage
- **File**: `apps/langconnect/langconnect/database/document.py`
- **Class**: `DocumentManager`
- **Current Issues**:
  - Multiple database connections per job
  - No connection pooling limits
  - Potential lock contention with concurrent inserts

## Problem Analysis

### 1. Resource Exhaustion Scenarios

#### Many Files (10+ files):
1. **Memory**: 10 files × base64 encoding = 2x memory usage per file
2. **CPU**: Sequential Docling processing blocks event loop
3. **Database**: Multiple concurrent insert operations
4. **Disk**: Temporary files accumulate without cleanup

#### Concurrent Uploads:
1. **Job Explosion**: User uploads 5 files, then 5 more = 10 concurrent jobs
2. **Database Pressure**: Multiple jobs hitting same connection pool
3. **Memory Competition**: Multiple file conversions in parallel
4. **Frontend Chaos**: Job tracking overwhelmed with updates

### 2. Performance Bottlenecks

#### Frontend:
- Sequential HTTP requests (network bottleneck)
- No upload progress aggregation
- State management race conditions

#### Backend:
- No job queue or prioritization
- Unlimited concurrency (resource exhaustion)
- Synchronous file processing within async context

## Implementation Plan

### Phase 1: Quick Wins (1-2 days)

#### 1.1 Frontend File Limits & Validation

**Objective**: Prevent system overload by implementing client-side limits and validation

**Files to modify:**
- `apps/web/src/features/rag/components/file-upload-section.tsx`
- `apps/web/src/features/rag/components/enhanced-upload-dialog.tsx`

**Detailed Implementation:**

**Step 1.1.1: Add Validation Constants**
```typescript
// Create new file: apps/web/src/features/rag/constants/upload-limits.ts
export const UPLOAD_LIMITS = {
  MAX_FILES_PER_UPLOAD: 10,
  MAX_TOTAL_SIZE_MB: 100,
  MAX_INDIVIDUAL_FILE_SIZE_MB: 25,
  SUPPORTED_FILE_TYPES: [
    'application/pdf',
    'text/plain',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'text/markdown',
    'text/csv'
  ]
} as const;

export const UPLOAD_MESSAGES = {
  TOO_MANY_FILES: (max: number) => 
    `Maximum ${max} files allowed per upload. Please select fewer files or upload in batches.`,
  TOTAL_SIZE_TOO_LARGE: (current: number, max: number) => 
    `Total file size (${current}MB) exceeds limit of ${max}MB. Please remove some files.`,
  INDIVIDUAL_FILE_TOO_LARGE: (filename: string, size: number, max: number) => 
    `File "${filename}" (${size}MB) exceeds individual file limit of ${max}MB.`,
  UNSUPPORTED_FILE_TYPE: (filename: string, type: string) => 
    `File "${filename}" has unsupported type "${type}". Please convert to a supported format.`
} as const;
```

**Step 1.1.2: Enhanced Validation Function**
```typescript
// Add to file-upload-section.tsx
interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

const validateUploadBatch = (files: File[]): ValidationResult => {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  // Check file count
  if (files.length > UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD) {
    errors.push(UPLOAD_MESSAGES.TOO_MANY_FILES(UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD));
  }
  
  // Check total size
  const totalSizeBytes = files.reduce((sum, file) => sum + file.size, 0);
  const totalSizeMB = Math.round(totalSizeBytes / (1024 * 1024));
  if (totalSizeMB > UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB) {
    errors.push(UPLOAD_MESSAGES.TOTAL_SIZE_TOO_LARGE(totalSizeMB, UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB));
  }
  
  // Check individual file sizes and types
  files.forEach(file => {
    const fileSizeMB = Math.round(file.size / (1024 * 1024));
    
    if (fileSizeMB > UPLOAD_LIMITS.MAX_INDIVIDUAL_FILE_SIZE_MB) {
      errors.push(UPLOAD_MESSAGES.INDIVIDUAL_FILE_TOO_LARGE(
        file.name, fileSizeMB, UPLOAD_LIMITS.MAX_INDIVIDUAL_FILE_SIZE_MB
      ));
    }
    
    if (!UPLOAD_LIMITS.SUPPORTED_FILE_TYPES.includes(file.type)) {
      warnings.push(UPLOAD_MESSAGES.UNSUPPORTED_FILE_TYPE(file.name, file.type));
    }
  });
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings
  };
};
```

**Step 1.1.3: UI Integration**
```typescript
// Enhanced file-upload-section.tsx
export function FileUploadSection({ files, onFilesChange }: FileUploadSectionProps) {
  const [validationResult, setValidationResult] = useState<ValidationResult>({ 
    isValid: true, errors: [], warnings: [] 
  });
  
  const handleFilesSelected = (newFiles: File[]) => {
    const validation = validateUploadBatch(newFiles);
    setValidationResult(validation);
    
    if (validation.isValid) {
      onFilesChange(newFiles);
    } else {
      // Show validation errors but don't update files
      toast.error("Upload validation failed", {
        description: validation.errors[0] // Show first error
      });
    }
  };
  
  return (
    <div className="space-y-4">
      {/* File drop zone */}
      <FileDropZone onFilesSelected={handleFilesSelected} />
      
      {/* Validation feedback */}
      {!validationResult.isValid && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Upload Issues</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4 space-y-1">
              {validationResult.errors.map((error, i) => (
                <li key={i}>{error}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      
      {/* Warnings */}
      {validationResult.warnings.length > 0 && (
        <Alert variant="warning">
          <Info className="h-4 w-4" />
          <AlertTitle>Upload Warnings</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4 space-y-1">
              {validationResult.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      
      {/* Upload summary */}
      {files.length > 0 && (
        <div className="bg-muted p-3 rounded-lg">
          <div className="flex justify-between text-sm">
            <span>{files.length} of {UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD} files selected</span>
            <span>{formatFileSize(files.reduce((sum, f) => sum + f.size, 0))} of {UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB}MB</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

#### 1.2 Fix Frontend Batching Architecture

**Objective**: Eliminate the 1-file-per-request pattern that creates job explosion

**File to modify:**
- `apps/web/src/features/rag/hooks/use-rag.tsx`

**Current Problem Analysis:**
```typescript
// BROKEN PATTERN: Creates N jobs for N files
async function uploadDocumentsEnhanced(collectionId, uploadData, authorization) {
  const results = [];
  
  // PROBLEM 1: Sequential HTTP requests
  for (const file of uploadData.files) {
    const formData = new FormData();
    formData.append("files", file, file.name);
    // PROBLEM 2: Individual API call per file
    const response = await fetch(url, { method: "POST", body: formData });
    results.push(await response.json());
  }
  
  // PROBLEM 3: Same pattern for URLs and text
  for (const urlItem of uploadData.urls) { /* separate request */ }
  if (uploadData.textContent.trim()) { /* separate request */ }
  
  return results; // Returns array of job IDs, not single job
}
```

**Solution Implementation:**
```typescript
// FIXED: Single batch request
async function uploadDocumentsEnhanced(
  collectionId: string,
  uploadData: UploadData,
  authorization: string,
): Promise<{ job_id: string; status: string; message: string }> {
  const url = `/api/langconnect/collections/${encodeURIComponent(collectionId)}/documents`;
  
  try {
    // Create single FormData with all content
    const formData = new FormData();
    
    // Add all files to single request
    uploadData.files.forEach(file => {
      formData.append("files", file, file.name);
    });
    
    // Add all URLs as comma-separated string
    if (uploadData.urls.length > 0) {
      const urlString = uploadData.urls.map(item => item.url).join(',');
      formData.append("urls", urlString);
    }
    
    // Add text content
    if (uploadData.textContent.trim()) {
      formData.append("text_content", uploadData.textContent.trim());
    }
    
    // Add processing configuration
    formData.append("processing_mode", uploadData.processingMode);
    
    // Generate intelligent title and description
    const itemCount = uploadData.files.length + uploadData.urls.length + (uploadData.textContent ? 1 : 0);
    formData.append("title", generateBatchTitle(uploadData, itemCount));
    formData.append("description", generateBatchDescription(uploadData));
    
    // Single HTTP request for entire batch
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      headers: {
        Authorization: `Bearer ${authorization}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Upload failed: ${errorData.detail || response.statusText}`);
    }

    // Returns single job ID instead of array
    return await response.json();
    
  } catch (error) {
    console.error("Batch upload error:", error);
    throw error;
  }
}

// Helper functions for intelligent naming
function generateBatchTitle(uploadData: UploadData, itemCount: number): string {
  if (itemCount === 1) {
    if (uploadData.files.length === 1) return uploadData.files[0].name;
    if (uploadData.urls.length === 1) return `Import: ${uploadData.urls[0].url}`;
    if (uploadData.textContent) return `Text: ${uploadData.textContent.substring(0, 30)}...`;
  }
  
  const parts: string[] = [];
  if (uploadData.files.length > 0) parts.push(`${uploadData.files.length} files`);
  if (uploadData.urls.length > 0) parts.push(`${uploadData.urls.length} URLs`);
  if (uploadData.textContent) parts.push('text content');
  
  return `Batch upload: ${parts.join(', ')}`;
}

function generateBatchDescription(uploadData: UploadData): string {
  const details: string[] = [];
  
  if (uploadData.files.length > 0) {
    const fileTypes = [...new Set(uploadData.files.map(f => f.type))];
    details.push(`Files: ${uploadData.files.map(f => f.name).join(', ')}`);
  }
  
  if (uploadData.urls.length > 0) {
    details.push(`URLs: ${uploadData.urls.map(u => u.url).join(', ')}`);
  }
  
  if (uploadData.textContent) {
    details.push(`Text content (${uploadData.textContent.length} characters)`);
  }
  
  return `Batch processed with ${uploadData.processingMode} mode. ${details.join(' | ')}`;
}
```

#### 1.3 Backend Concurrency Management

**Objective**: Prevent resource exhaustion by limiting concurrent processing jobs

**Files to modify:**
- `apps/langconnect/langconnect/services/job_service.py`
- `apps/langconnect/langconnect/models/job.py` (for new queue-related models)

**Step 1.3.1: Enhanced Job Service with Queue Management**
```python
# Enhanced job_service.py
import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

@dataclass
class QueuedJob:
    job_id: str
    runtime_data: Optional[dict]
    priority: int = 0  # Higher number = higher priority
    queued_at: datetime
    estimated_duration: int = 60  # seconds

class JobService:
    def __init__(self):
        self.running_jobs: Dict[str, asyncio.Task] = {}
        self.job_queue: deque[QueuedJob] = deque()
        self.max_concurrent_jobs = 3
        self.queue_processor_task: Optional[asyncio.Task] = None
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
                if len(self.running_jobs) < self.max_concurrent_jobs and self.job_queue:
                    # Get highest priority job from queue
                    queued_job = self._get_next_job_from_queue()
                    if queued_job:
                        await self._start_job_immediately(queued_job.job_id, queued_job.runtime_data)
                        logger.info(f"Started queued job {queued_job.job_id} (waited {(datetime.now(UTC) - queued_job.queued_at).total_seconds():.1f}s)")
                
                # Check every 2 seconds
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(5)  # Wait longer on errors
    
    def _get_next_job_from_queue(self) -> Optional[QueuedJob]:
        """Get the highest priority job from queue"""
        if not self.job_queue:
            return None
        
        # Sort by priority (descending) then by queued time (ascending)
        sorted_jobs = sorted(self.job_queue, key=lambda j: (-j.priority, j.queued_at))
        next_job = sorted_jobs[0]
        self.job_queue.remove(next_job)
        return next_job
    
    def _calculate_job_priority(self, job_data: dict) -> int:
        """Calculate job priority based on content"""
        priority = 0
        
        # Text-only jobs get higher priority (faster to process)
        if job_data.get('text_content') and not job_data.get('files') and not job_data.get('urls'):
            priority += 10
        
        # Fewer files = higher priority
        file_count = len(job_data.get('files', []))
        if file_count <= 2:
            priority += 5
        elif file_count <= 5:
            priority += 2
        
        # Fast processing mode gets slight priority boost
        if job_data.get('processing_mode') == 'fast':
            priority += 1
        
        return priority
    
    async def start_job_processing(self, job_id: str, runtime_data: dict = None) -> bool:
        """Start job processing with concurrency management"""
        if job_id in self.running_jobs:
            logger.warning(f"Job {job_id} is already running")
            return False
        
        # Check if we can start immediately
        if len(self.running_jobs) < self.max_concurrent_jobs:
            return await self._start_job_immediately(job_id, runtime_data)
        
        # Queue the job if at capacity
        priority = self._calculate_job_priority(runtime_data or {})
        queued_job = QueuedJob(
            job_id=job_id,
            runtime_data=runtime_data,
            priority=priority,
            queued_at=datetime.now(UTC)
        )
        
        self.job_queue.append(queued_job)
        
        # Update job status to indicate queuing
        await self.update_job_progress(job_id, JobUpdate(
            status=JobStatus.PENDING,
            current_step=f"Queued (position {len(self.job_queue)}, {len(self.running_jobs)} jobs running)"
        ))
        
        logger.info(f"Job {job_id} queued with priority {priority} (queue size: {len(self.job_queue)})")
        return True
    
    async def _start_job_immediately(self, job_id: str, runtime_data: dict = None) -> bool:
        """Start job processing immediately"""
        try:
            # Create and start the processing task
            task = asyncio.create_task(self._process_job(job_id, runtime_data))
            self.running_jobs[job_id] = task
            
            # Add callback to clean up completed tasks and process queue
            def on_job_complete(completed_task):
                self.running_jobs.pop(job_id, None)
                logger.info(f"Job {job_id} completed, {len(self.running_jobs)} jobs still running")
                
                # Log queue status
                if self.job_queue:
                    logger.info(f"Queue status: {len(self.job_queue)} jobs waiting")
            
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
            "queued_jobs": len(self.job_queue),
            "queue_details": [
                {
                    "job_id": job.job_id,
                    "priority": job.priority,
                    "queued_for_seconds": (datetime.now(UTC) - job.queued_at).total_seconds()
                }
                for job in sorted(self.job_queue, key=lambda j: (-j.priority, j.queued_at))
            ]
        }
```

**Step 1.3.2: Queue Status API Endpoint**
```python
# Add to apps/langconnect/langconnect/api/jobs.py
@router.get("/queue/status", response_model=dict[str, Any])
async def get_queue_status(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get current job queue status"""
    status = job_service.get_queue_status()
    return {
        "queue_status": status,
        "message": f"{status['running_jobs']} jobs running, {status['queued_jobs']} queued"
    }
```

#### 1.4 Enhanced Error Handling & User Feedback

**Objective**: Provide clear feedback when limits are hit and jobs are queued

**Files to modify:**
- `apps/web/src/utils/upload-toasts.ts`
- `apps/web/src/hooks/use-job-tracking.ts`

**Implementation:**
```typescript
// Enhanced upload-toasts.ts
export const uploadToasts = {
  started: (params: UploadStartedParams) => {
    const itemDescription = getItemCountDescription(params.sources);
    const modeDisplay = getProcessingModeDisplay(params.processingMode);
    
    toast(`Upload started: Processing ${itemDescription}`, {
      description: `Using ${modeDisplay} processing mode`,
      id: 'upload-progress',
      duration: 3000,
      icon: '⏳'
    });
  },
  
  // NEW: Queue status toast
  queued: (position: number, estimatedWait: number) => {
    toast.info("Upload queued", {
      description: `Position ${position} in queue. Estimated wait: ${Math.round(estimatedWait / 60)} minutes`,
      duration: 8000,
      action: {
        label: 'View Queue',
        onClick: () => {
          // Could open a queue status dialog
        }
      }
    });
  },
  
  // NEW: System busy toast
  systemBusy: (activeJobs: number, maxJobs: number) => {
    toast.warning("System busy", {
      description: `${activeJobs} of ${maxJobs} processing slots in use. Your upload will start automatically when a slot becomes available.`,
      duration: 10000
    });
  }
};
```

### Phase 2: Backend Optimisation (3-4 days)

#### 2.1 Parallel File Processing Within Jobs

**Objective**: Process multiple files within a single job concurrently while maintaining resource limits

**Files to modify:**
- `apps/langconnect/langconnect/services/enhanced_document_processor.py`
- `apps/langconnect/langconnect/services/enhanced_chunking_service.py`

**Step 2.1.1: Parallel File Processing Architecture**
```python
# Enhanced enhanced_document_processor.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
import psutil
import resource

class EnhancedDocumentProcessor:
    def __init__(self):
        self.docling_service = DoclingConverterService()
        self.chunking_service = EnhancedChunkingService()
        # NEW: Resource-aware processing limits
        self.max_concurrent_files = min(3, max(1, psutil.cpu_count() // 2))
        self.max_memory_usage_mb = 1024  # 1GB limit per job
        self.thread_pool = ThreadPoolExecutor(max_workers=2)  # For CPU-bound operations
    
    async def _process_files(
        self,
        files: List[Union[Dict[str, Any], UploadFile]],
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable] = None,
        document_manager: Optional[DocumentManager] = None
    ) -> ProcessingResult:
        """Process files with intelligent parallel processing"""
        
        try:
            # Pre-flight resource check
            available_memory = self._get_available_memory_mb()
            if available_memory < 500:  # Require at least 500MB
                logger.warning(f"Low memory available ({available_memory}MB), processing sequentially")
                return await self._process_files_sequential(files, title, description, processing_options, progress_callback, document_manager)
            
            # Duplicate detection (existing code...)
            # [Previous duplicate detection code remains the same]
            
            # Determine processing strategy based on file count and size
            total_size = sum(self._estimate_file_size(f) for f in files_to_process)
            should_process_parallel = (
                len(files_to_process) > 1 and 
                len(files_to_process) <= self.max_concurrent_files and
                total_size < self.max_memory_usage_mb * 1024 * 1024
            )
            
            if should_process_parallel:
                logger.info(f"Processing {len(files_to_process)} files in parallel (estimated {total_size // (1024*1024)}MB)")
                return await self._process_files_parallel(files_to_process, title, description, processing_options, progress_callback, document_manager)
            else:
                logger.info(f"Processing {len(files_to_process)} files sequentially (size limit or resource constraints)")
                return await self._process_files_sequential(files_to_process, title, description, processing_options, progress_callback, document_manager)
                
        except Exception as e:
            logger.error(f"🚨 File processing failed: {e}")
            return ProcessingResult(
                documents=[],
                metadata={},
                success=False,
                error_message=str(e)
            )
    
    async def _process_files_parallel(
        self, 
        files: List[Union[Dict[str, Any], UploadFile]], 
        title: str,
        description: str,
        processing_options: ProcessingOptions,
        progress_callback: Optional[callable],
        document_manager: Optional[DocumentManager]
    ) -> ProcessingResult:
        """Process multiple files concurrently with resource management"""
        
        # Create semaphore to limit concurrent file processing
        semaphore = asyncio.Semaphore(self.max_concurrent_files)
        
        # Track progress
        completed_files = 0
        total_files = len(files)
        all_documents = []
        all_document_records = []
        processing_errors = []
        
        async def process_single_file_with_semaphore(file_obj, file_index):
            async with semaphore:
                try:
                    # Update progress
                    if progress_callback:
                        progress_callback(f"Processing file {file_index + 1}/{total_files}: {getattr(file_obj, 'filename', 'unknown')}")
                    
                    # Monitor memory usage before processing
                    memory_before = self._get_memory_usage_mb()
                    if memory_before > self.max_memory_usage_mb * 0.8:  # 80% threshold
                        logger.warning(f"High memory usage ({memory_before}MB), waiting for cleanup")
                        await asyncio.sleep(2)  # Brief pause for GC
                    
                    # Process the file
                    result = await self._process_single_file(
                        file_obj, processing_options, document_manager, 
                        title=title, description=description
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
                    
                    # Update overall progress
                    progress_percent = int((completed_files / total_files) * 100)
                    if progress_callback:
                        progress_callback(f"Completed {completed_files}/{total_files} files ({progress_percent}%)")
                    
                except Exception as e:
                    processing_errors.append(str(e))
                    completed_files += 1
            
            # Final result compilation
            success = len(processing_errors) == 0
            error_message = "; ".join(processing_errors) if processing_errors else None
            
            return ProcessingResult(
                documents=all_documents,
                metadata={
                    "processing_mode": processing_options.processing_mode,
                    "files_processed": completed_files,
                    "parallel_processing": True,
                    "errors": processing_errors if processing_errors else None
                },
                success=success,
                error_message=error_message,
                document_records=all_document_records if all_document_records else None
            )
            
        except Exception as e:
            logger.error(f"Parallel processing failed: {e}")
            return ProcessingResult(
                documents=[],
                metadata={"processing_mode": processing_options.processing_mode},
                success=False,
                error_message=f"Parallel processing failed: {str(e)}"
            )
    
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
```

#### 2.2 Streaming & Memory Management

**Objective**: Handle large files without exhausting system memory

**Step 2.2.1: Streaming File Processing**
```python
# Enhanced file handling in enhanced_document_processor.py
import tempfile
import aiofiles
from contextlib import asynccontextmanager

class EnhancedDocumentProcessor:
    
    @asynccontextmanager
    async def _get_file_stream(self, file_obj):
        """Context manager for safe file streaming"""
        temp_file = None
        try:
            if hasattr(file_obj, 'content_b64'):
                # Handle base64 encoded files from job data
                import base64
                content = base64.b64decode(file_obj['content_b64'])
                
                # Stream large files to disk
                if len(content) > 50 * 1024 * 1024:  # 50MB threshold
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    temp_file.write(content)
                    temp_file.flush()
                    yield temp_file.name
                else:
                    # Keep small files in memory
                    temp_file = tempfile.NamedTemporaryFile()
                    temp_file.write(content)
                    temp_file.flush()
                    yield temp_file.name
            else:
                # Handle UploadFile objects
                if hasattr(file_obj, 'size') and file_obj.size > 50 * 1024 * 1024:
                    # Stream large uploads to disk
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    async with aiofiles.open(temp_file.name, 'wb') as f:
                        while chunk := await file_obj.read(8192):  # 8KB chunks
                            await f.write(chunk)
                    yield temp_file.name
                else:
                    # Read small files into memory
                    content = await file_obj.read()
                    temp_file = tempfile.NamedTemporaryFile()
                    temp_file.write(content)
                    temp_file.flush()
                    yield temp_file.name
                    
        finally:
            if temp_file:
                try:
                    if hasattr(temp_file, 'close'):
                        temp_file.close()
                    if hasattr(temp_file, 'name') and os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
    
    async def _process_single_file(
        self, 
        file_obj, 
        processing_options: ProcessingOptions,
        document_manager: Optional[DocumentManager] = None,
        title: str = "",
        description: str = ""
    ) -> Dict[str, Any]:
        """Process a single file with streaming support"""
        
        async with self._get_file_stream(file_obj) as file_path:
            try:
                # Use file path for processing to avoid memory issues
                conversion_result = await self.docling_service.convert_document(
                    file_path=file_path,
                    processing_options=processing_options
                )
                
                # Convert to documents
                documents = self._convert_docling_result_to_documents(
                    conversion_result,
                    source_name=getattr(file_obj, 'filename', 'unknown'),
                    title=title,
                    description=description
                )
                
                # Chunk documents if needed
                if documents:
                    chunked_documents = await self.chunking_service.chunk_documents(
                        documents,
                        chunking_strategy=processing_options.chunking_strategy
                    )
                    
                    # Store in document model if manager available
                    document_records = []
                    if document_manager:
                        for doc in chunked_documents:
                            record = await self._store_document_with_chunks(
                                doc, document_manager, file_obj
                            )
                            if record:
                                document_records.append(record)
                    
                    return {
                        "documents": chunked_documents,
                        "document_records": document_records
                    }
                
                return {"documents": [], "document_records": []}
                
            except Exception as e:
                logger.error(f"Failed to process file {getattr(file_obj, 'filename', 'unknown')}: {e}")
                raise
```

#### 2.3 Database Connection Pooling & Optimisation

**Objective**: Handle concurrent database operations efficiently

**Files to modify:**
- `apps/langconnect/langconnect/database/connection.py`
- `apps/langconnect/langconnect/services/job_service.py`

**Step 2.3.1: Enhanced Connection Pool Configuration**
```python
# Enhanced connection.py
import asyncpg
import asyncio
from contextlib import asynccontextmanager
import logging

class DatabaseConnectionManager:
    def __init__(self):
        self.pool = None
        self.pool_config = {
            "min_size": 5,
            "max_size": 20,  # Increased for concurrent jobs
            "command_timeout": 120,  # Longer timeout for large operations
            "server_settings": {
                "application_name": "langconnect_enhanced",
                "statement_timeout": "120s",
                "idle_in_transaction_session_timeout": "300s",
            }
        }
    
    async def initialize_pool(self):
        """Initialize the connection pool with optimised settings"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    **self.pool_config
                )
                logger.info(f"Database pool initialized: {self.pool_config['min_size']}-{self.pool_config['max_size']} connections")
            except Exception as e:
                logger.error(f"Failed to initialize database pool: {e}")
                raise
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection with automatic cleanup"""
        if self.pool is None:
            await self.initialize_pool()
        
        connection = None
        try:
            connection = await self.pool.acquire()
            yield connection
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                await self.pool.release(connection)

# Global connection manager instance
db_manager = DatabaseConnectionManager()

async def get_db_connection():
    """Get database connection (updated interface)"""
    return db_manager.get_connection()
```

**Step 2.3.2: Batch Database Operations**
```python
# Enhanced document storage operations
class DocumentManager:
    
    async def create_documents_batch(
        self, 
        documents_data: List[Dict[str, Any]]
    ) -> List[str]:
        """Create multiple documents in a single transaction"""
        if not documents_data:
            return []
        
        async with get_db_connection() as conn:
            async with conn.transaction():
                document_ids = []
                
                # Prepare batch insert
                insert_query = """
                    INSERT INTO langconnect.langchain_pg_document 
                    (id, collection_id, content, cmetadata, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, NOW(), NOW())
                    RETURNING id
                """
                
                for doc_data in documents_data:
                    result = await conn.fetchrow(
                        insert_query,
                        doc_data['id'],
                        self.collection_id,
                        doc_data['content'],
                        json.dumps(doc_data['metadata'])
                    )
                    document_ids.append(str(result['id']))
                
                logger.info(f"Created {len(document_ids)} documents in batch")
                return document_ids
    
    async def create_chunks_batch(
        self, 
        chunks_data: List[Dict[str, Any]]
    ) -> List[str]:
        """Create multiple chunks in a single transaction"""
        if not chunks_data:
            return []
        
        async with get_db_connection() as conn:
            # Use COPY for very large batch inserts
            if len(chunks_data) > 100:
                return await self._create_chunks_copy(conn, chunks_data)
            else:
                return await self._create_chunks_insert(conn, chunks_data)
```

#### 2.4 Progressive Upload Support & Error Handling

**Objective**: Allow larger uploads through intelligent batching and robust error handling

**Files to modify:**
- `apps/web/src/features/rag/components/enhanced-upload-dialog.tsx`
- `apps/web/src/features/rag/hooks/use-rag.tsx`
- `apps/langconnect/langconnect/services/job_service.py`

**Step 2.4.1: Progressive Upload Implementation**
```typescript
// Enhanced upload-dialog.tsx
interface ProgressiveBatch {
  id: string;
  files: File[];
  status: 'pending' | 'processing' | 'completed' | 'failed';
  jobId?: string;
  error?: string;
}

export function EnhancedUploadDialog({ open, onOpenChange, onSubmit, collectionId }: EnhancedUploadDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [processingBatches, setProcessingBatches] = useState<ProgressiveBatch[]>([]);
  const [isProgressiveMode, setIsProgressiveMode] = useState(false);
  
  // Check if progressive mode is needed
  useEffect(() => {
    const needsProgressive = files.length > UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD;
    setIsProgressiveMode(needsProgressive);
    
    if (needsProgressive) {
      // Create batches
      const batches: ProgressiveBatch[] = [];
      for (let i = 0; i < files.length; i += UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD) {
        const batchFiles = files.slice(i, i + UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD);
        batches.push({
          id: `batch-${i / UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD + 1}`,
          files: batchFiles,
          status: 'pending'
        });
      }
      setProcessingBatches(batches);
    }
  }, [files]);
  
  const handleProgressiveSubmit = async () => {
    if (!isProgressiveMode) {
      return handleSubmit();
    }
    
    setSubmitting(true);
    
    try {
      // Process batches sequentially
      for (let i = 0; i < processingBatches.length; i++) {
        const batch = processingBatches[i];
        
        // Update batch status
        setProcessingBatches(prev => prev.map(b => 
          b.id === batch.id ? { ...b, status: 'processing' } : b
        ));
        
        try {
          const uploadData: UploadData = {
            files: batch.files,
            urls: [],
            textContent: '',
            processingMode
          };
          
          // Show batch-specific toast
          uploadToasts.batchStarted(i + 1, processingBatches.length, batch.files.length);
          
          const result = await onSubmit(uploadData);
          
          // Update batch with success
          setProcessingBatches(prev => prev.map(b => 
            b.id === batch.id ? { ...b, status: 'completed', jobId: result.job_id } : b
          ));
          
          uploadToasts.batchCompleted(i + 1, processingBatches.length);
          
        } catch (error) {
          // Update batch with error
          setProcessingBatches(prev => prev.map(b => 
            b.id === batch.id ? { ...b, status: 'failed', error: error.message } : b
          ));
          
          uploadToasts.batchFailed(i + 1, processingBatches.length, error);
          
          // Continue with next batch or stop based on user preference
          const shouldContinue = await showBatchErrorDialog(batch, error);
          if (!shouldContinue) break;
        }
        
        // Brief pause between batches to avoid overwhelming the system
        if (i < processingBatches.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
      }
      
      // Show final summary
      const completedBatches = processingBatches.filter(b => b.status === 'completed').length;
      const totalBatches = processingBatches.length;
      
      if (completedBatches === totalBatches) {
        uploadToasts.allBatchesCompleted(totalBatches, files.length);
      } else {
        uploadToasts.batchesSummary(completedBatches, totalBatches, files.length);
      }
      
      // Reset and close
      resetForm();
      onOpenChange(false);
      
    } finally {
      setSubmitting(false);
    }
  };
}
```

**Step 2.4.2: Enhanced Error Handling & Partial Success**
```python
# Enhanced job_service.py error handling
class JobService:
    
    async def _process_job(self, job_id: str, runtime_data: dict = None) -> None:
        """Enhanced job processing with partial success handling"""
        
        try:
            # Update job status to processing
            await self.update_job_progress(job_id, JobUpdate(
                status=JobStatus.PROCESSING,
                current_step="Initializing processing"
            ))
            
            # Get job details
            job_response = await self.get_job(job_id, "system", is_service_account=True)
            if not job_response:
                raise Exception(f"Job {job_id} not found")
            
            # Initialize processor
            processor = EnhancedDocumentProcessor()
            
            # Process with detailed error tracking
            results = []
            errors = []
            partial_success = False
            
            try:
                # Main processing logic
                processing_result = await processor.process_input(
                    input_data=job_response.input_data,
                    processing_options=job_response.processing_options,
                    progress_callback=lambda msg: asyncio.create_task(
                        self.update_job_progress(job_id, JobUpdate(current_step=msg))
                    ),
                    collection_id=str(job_response.collection_id),
                    user_id=job_response.user_id,
                    use_document_model=True
                )
                
                # Check for partial success
                if processing_result.success:
                    # Complete success
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.COMPLETED,
                        progress_percentage=100,
                        current_step="Processing completed successfully",
                        documents_processed=len(processing_result.documents),
                        chunks_created=sum(len(doc.page_content.split()) for doc in processing_result.documents),
                        output_data={
                            "documents_created": len(processing_result.documents),
                            "processing_summary": processing_result.metadata,
                            "duplicate_summary": processing_result.duplicate_summary,
                            "files_skipped": processing_result.files_skipped,
                            "files_overwritten": processing_result.files_overwritten
                        }
                    ))
                    
                elif processing_result.documents and processing_result.error_message:
                    # Partial success - some files processed, some failed
                    partial_success = True
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.COMPLETED,  # Still mark as completed
                        progress_percentage=100,
                        current_step="Processing completed with some errors",
                        documents_processed=len(processing_result.documents),
                        chunks_created=sum(len(doc.page_content.split()) for doc in processing_result.documents),
                        error_message=f"Partial success: {processing_result.error_message}",
                        output_data={
                            "documents_created": len(processing_result.documents),
                            "processing_summary": processing_result.metadata,
                            "partial_success": True,
                            "error_details": processing_result.error_message,
                            "duplicate_summary": processing_result.duplicate_summary,
                            "files_skipped": processing_result.files_skipped,
                            "files_overwritten": processing_result.files_overwritten
                        }
                    ))
                    
                else:
                    # Complete failure
                    await self.update_job_progress(job_id, JobUpdate(
                        status=JobStatus.FAILED,
                        current_step="Processing failed",
                        error_message=processing_result.error_message or "Unknown processing error",
                        error_details={
                            "processing_metadata": processing_result.metadata,
                            "duplicate_summary": processing_result.duplicate_summary
                        }
                    ))
                
            except Exception as processing_error:
                logger.error(f"Job {job_id} processing error: {processing_error}")
                await self.update_job_progress(job_id, JobUpdate(
                    status=JobStatus.FAILED,
                    current_step="Processing failed with exception",
                    error_message=str(processing_error),
                    error_details={"exception_type": type(processing_error).__name__}
                ))
                
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self.update_job_progress(job_id, JobUpdate(
                status=JobStatus.FAILED,
                error_message=str(e)
            ))
        
        finally:
            # Cleanup and resource management
            if hasattr(processor, 'cleanup'):
                processor.cleanup()
```

### Phase 3: Advanced Features (1 week)

#### 3.1 Smart Batching & Intelligent Load Balancing

**Objective**: Implement dynamic batch sizing and intelligent job distribution based on system resources and content characteristics

**Files to modify:**
- `apps/langconnect/langconnect/services/smart_batching_service.py` (new)
- `apps/langconnect/langconnect/services/job_service.py`
- `apps/web/src/features/rag/hooks/use-smart-upload.tsx` (new)

**Step 3.1.1: Smart Batching Service**
```python
# Create new file: apps/langconnect/langconnect/services/smart_batching_service.py
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum
import psutil
import logging

logger = logging.getLogger(__name__)

class FileComplexity(Enum):
    """File complexity levels for processing estimation"""
    SIMPLE = "simple"      # Plain text, small PDFs
    MODERATE = "moderate"  # Standard documents, presentations
    COMPLEX = "complex"    # Large PDFs with images, scanned documents
    HEAVY = "heavy"        # Very large files, complex layouts

@dataclass
class FileAnalysis:
    """Analysis of a file for batching decisions"""
    filename: str
    size_mb: float
    complexity: FileComplexity
    estimated_processing_time: int  # seconds
    estimated_memory_mb: int
    file_type: str

@dataclass
class BatchPlan:
    """Plan for processing a batch of files"""
    batch_id: str
    files: List[FileAnalysis]
    estimated_total_time: int
    estimated_peak_memory: int
    priority: int
    processing_strategy: str  # 'parallel', 'sequential', 'hybrid'

class SmartBatchingService:
    """Service for intelligent file batching and resource allocation"""
    
    def __init__(self):
        self.complexity_thresholds = {
            FileComplexity.SIMPLE: {"max_size_mb": 5, "base_time": 10},
            FileComplexity.MODERATE: {"max_size_mb": 25, "base_time": 30},
            FileComplexity.COMPLEX: {"max_size_mb": 100, "base_time": 120},
            FileComplexity.HEAVY: {"max_size_mb": float('inf'), "base_time": 300}
        }
        
        # System resource limits
        self.max_batch_memory_mb = 1500  # 1.5GB per batch
        self.max_batch_time_minutes = 15  # 15 minutes max per batch
        self.target_batch_time_minutes = 8  # Target 8 minutes per batch
    
    def analyze_file(self, file_obj) -> FileAnalysis:
        """Analyze a single file to determine its processing characteristics"""
        
        # Get file size
        size_mb = self._get_file_size_mb(file_obj)
        
        # Determine file type
        file_type = getattr(file_obj, 'content_type', 'unknown')
        filename = getattr(file_obj, 'filename', 'unknown')
        
        # Assess complexity based on size and type
        complexity = self._assess_file_complexity(size_mb, file_type, filename)
        
        # Estimate processing time and memory
        estimated_time = self._estimate_processing_time(size_mb, complexity, file_type)
        estimated_memory = self._estimate_memory_usage(size_mb, complexity)
        
        return FileAnalysis(
            filename=filename,
            size_mb=size_mb,
            complexity=complexity,
            estimated_processing_time=estimated_time,
            estimated_memory_mb=estimated_memory,
            file_type=file_type
        )
    
    def create_optimal_batches(self, file_analyses: List[FileAnalysis]) -> List[BatchPlan]:
        """Create optimal batches from analyzed files"""
        
        if not file_analyses:
            return []
        
        # Sort files by complexity and size for optimal grouping
        sorted_files = sorted(file_analyses, key=lambda f: (f.complexity.value, f.size_mb))
        
        batches = []
        current_batch_files = []
        current_batch_memory = 0
        current_batch_time = 0
        batch_counter = 1
        
        for file_analysis in sorted_files:
            # Check if adding this file would exceed limits
            would_exceed_memory = (current_batch_memory + file_analysis.estimated_memory_mb) > self.max_batch_memory_mb
            would_exceed_time = (current_batch_time + file_analysis.estimated_processing_time) > (self.max_batch_time_minutes * 60)
            
            # Start new batch if limits would be exceeded or if batch is getting large
            if (would_exceed_memory or would_exceed_time or len(current_batch_files) >= 8) and current_batch_files:
                # Create batch from current files
                batch = self._create_batch_plan(f"batch-{batch_counter}", current_batch_files)
                batches.append(batch)
                
                # Reset for new batch
                current_batch_files = []
                current_batch_memory = 0
                current_batch_time = 0
                batch_counter += 1
            
            # Add file to current batch
            current_batch_files.append(file_analysis)
            current_batch_memory += file_analysis.estimated_memory_mb
            current_batch_time += file_analysis.estimated_processing_time
        
        # Create final batch if there are remaining files
        if current_batch_files:
            batch = self._create_batch_plan(f"batch-{batch_counter}", current_batch_files)
            batches.append(batch)
        
        # Optimize batch priorities and strategies
        self._optimize_batch_strategies(batches)
        
        return batches
    
    def _assess_file_complexity(self, size_mb: float, file_type: str, filename: str) -> FileComplexity:
        """Assess file complexity based on size, type, and characteristics"""
        
        # Large files are generally more complex
        if size_mb > 100:
            return FileComplexity.HEAVY
        elif size_mb > 25:
            return FileComplexity.COMPLEX
        
        # File type-based complexity
        if file_type in ['text/plain', 'text/markdown', 'text/csv']:
            return FileComplexity.SIMPLE
        elif file_type in ['application/pdf']:
            # PDFs can vary widely
            if size_mb > 50:
                return FileComplexity.COMPLEX
            elif size_mb > 10:
                return FileComplexity.MODERATE
            else:
                return FileComplexity.SIMPLE
        elif file_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                          'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
            return FileComplexity.MODERATE
        
        # Check filename for indicators
        filename_lower = filename.lower()
        if any(indicator in filename_lower for indicator in ['scan', 'scanned', 'image', 'photo']):
            return FileComplexity.COMPLEX
        
        # Default to moderate for unknown types
        return FileComplexity.MODERATE
    
    def _estimate_processing_time(self, size_mb: float, complexity: FileComplexity, file_type: str) -> int:
        """Estimate processing time in seconds"""
        
        base_time = self.complexity_thresholds[complexity]["base_time"]
        
        # Size factor (larger files take longer)
        size_factor = 1 + (size_mb / 10)  # +10% per 10MB
        
        # Type-specific adjustments
        type_multiplier = 1.0
        if file_type == 'application/pdf':
            type_multiplier = 1.5  # PDFs are slower to process
        elif 'image' in file_type:
            type_multiplier = 2.0  # Images require OCR
        
        estimated_time = int(base_time * size_factor * type_multiplier)
        
        # Cap at reasonable maximums
        return min(estimated_time, 600)  # Max 10 minutes per file
    
    def _estimate_memory_usage(self, size_mb: float, complexity: FileComplexity) -> int:
        """Estimate memory usage in MB"""
        
        # Base memory usage
        base_memory = {
            FileComplexity.SIMPLE: 50,
            FileComplexity.MODERATE: 100,
            FileComplexity.COMPLEX: 200,
            FileComplexity.HEAVY: 400
        }[complexity]
        
        # File size factor (larger files need more memory)
        size_memory = size_mb * 2  # 2MB RAM per 1MB file (processing overhead)
        
        total_memory = base_memory + size_memory
        
        # Cap at reasonable maximum
        return min(int(total_memory), 800)  # Max 800MB per file
    
    def _create_batch_plan(self, batch_id: str, files: List[FileAnalysis]) -> BatchPlan:
        """Create a batch plan from a list of files"""
        
        total_time = sum(f.estimated_processing_time for f in files)
        peak_memory = max(sum(f.estimated_memory_mb for f in files[:3]), 
                         max(f.estimated_memory_mb for f in files) if files else 0)
        
        # Determine processing strategy
        strategy = self._determine_processing_strategy(files, peak_memory)
        
        # Calculate priority (smaller, simpler batches get higher priority)
        priority = self._calculate_batch_priority(files, total_time)
        
        return BatchPlan(
            batch_id=batch_id,
            files=files,
            estimated_total_time=total_time,
            estimated_peak_memory=peak_memory,
            priority=priority,
            processing_strategy=strategy
        )
    
    def _determine_processing_strategy(self, files: List[FileAnalysis], peak_memory: int) -> str:
        """Determine the best processing strategy for a batch"""
        
        if len(files) == 1:
            return "sequential"
        
        # If memory usage is high, use sequential processing
        if peak_memory > 1000:  # 1GB threshold
            return "sequential"
        
        # If all files are simple, use parallel processing
        if all(f.complexity == FileComplexity.SIMPLE for f in files):
            return "parallel"
        
        # Mixed complexity - use hybrid approach
        if len(files) <= 4:
            return "parallel"
        else:
            return "hybrid"
    
    def _calculate_batch_priority(self, files: List[FileAnalysis], total_time: int) -> int:
        """Calculate batch priority (higher number = higher priority)"""
        
        priority = 100  # Base priority
        
        # Smaller batches get higher priority
        priority += max(0, 10 - len(files)) * 5
        
        # Shorter estimated time gets higher priority
        priority += max(0, 300 - total_time) // 30  # +1 per 30 seconds under 5 minutes
        
        # Simple files get slight priority boost
        simple_files = sum(1 for f in files if f.complexity == FileComplexity.SIMPLE)
        priority += simple_files * 2
        
        return priority
    
    def _get_file_size_mb(self, file_obj) -> float:
        """Get file size in MB"""
        if hasattr(file_obj, 'size') and file_obj.size:
            return file_obj.size / (1024 * 1024)
        elif hasattr(file_obj, 'content_b64'):
            # Estimate from base64 content
            return len(file_obj['content_b64']) * 3 / 4 / (1024 * 1024)
        else:
            return 1.0  # 1MB default
    
    def _optimize_batch_strategies(self, batches: List[BatchPlan]):
        """Optimize processing strategies across all batches"""
        
        # Sort batches by priority
        batches.sort(key=lambda b: b.priority, reverse=True)
        
        # Adjust strategies based on system load and batch sequence
        for i, batch in enumerate(batches):
            # First few batches can be more aggressive
            if i < 2 and batch.processing_strategy == "sequential" and len(batch.files) <= 3:
                batch.processing_strategy = "parallel"
```

#### 3.2 Resource Monitoring & Adaptive Scaling

**Objective**: Implement real-time resource monitoring and adaptive job scheduling

**Files to create:**
- `apps/langconnect/langconnect/services/resource_monitor.py`
- `apps/langconnect/langconnect/services/adaptive_scheduler.py`

**Step 3.2.1: Resource Monitoring Service**
```python
# Create new file: apps/langconnect/langconnect/services/resource_monitor.py
import asyncio
import psutil
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@dataclass
class SystemResources:
    """Current system resource usage"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_mb: int
    disk_usage_percent: float
    active_connections: int
    load_average: Optional[float] = None

@dataclass
class ResourceThresholds:
    """Resource usage thresholds for different actions"""
    cpu_warning: float = 70.0
    cpu_critical: float = 85.0
    memory_warning: float = 75.0
    memory_critical: float = 90.0
    disk_warning: float = 80.0
    disk_critical: float = 95.0

class ResourceMonitor:
    """Real-time system resource monitoring service"""
    
    def __init__(self):
        self.thresholds = ResourceThresholds()
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.resource_history: List[SystemResources] = []
        self.max_history_size = 100  # Keep last 100 readings
        self.alert_callbacks: List[Callable] = []
        self.last_alert_time: Dict[str, datetime] = {}
        self.alert_cooldown = timedelta(minutes=5)  # 5-minute cooldown between alerts
    
    async def start_monitoring(self, interval_seconds: int = 10):
        """Start continuous resource monitoring"""
        if self.monitoring:
            logger.warning("Resource monitoring already started")
            return
        
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop(interval_seconds))
        logger.info(f"Started resource monitoring with {interval_seconds}s interval")
    
    async def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped resource monitoring")
    
    async def _monitoring_loop(self, interval_seconds: int):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Collect current resource usage
                resources = await self._collect_resources()
                
                # Add to history
                self.resource_history.append(resources)
                if len(self.resource_history) > self.max_history_size:
                    self.resource_history.pop(0)
                
                # Check for threshold violations
                await self._check_thresholds(resources)
                
                # Wait for next interval
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in resource monitoring loop: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def _collect_resources(self) -> SystemResources:
        """Collect current system resource usage"""
        
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_mb = memory.available // (1024 * 1024)
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_usage_percent = disk.percent
        
        # Get network connections (as proxy for active database connections)
        try:
            connections = len(psutil.net_connections())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            connections = 0
        
        # Get load average (Unix systems only)
        load_average = None
        try:
            load_average = psutil.getloadavg()[0]  # 1-minute load average
        except (AttributeError, OSError):
            pass  # Not available on Windows
        
        return SystemResources(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_available_mb=memory_available_mb,
            disk_usage_percent=disk_usage_percent,
            active_connections=connections,
            load_average=load_average
        )
    
    async def _check_thresholds(self, resources: SystemResources):
        """Check resource usage against thresholds and trigger alerts"""
        
        alerts = []
        
        # Check CPU usage
        if resources.cpu_percent >= self.thresholds.cpu_critical:
            alerts.append(("cpu_critical", f"CPU usage critical: {resources.cpu_percent:.1f}%"))
        elif resources.cpu_percent >= self.thresholds.cpu_warning:
            alerts.append(("cpu_warning", f"CPU usage high: {resources.cpu_percent:.1f}%"))
        
        # Check memory usage
        if resources.memory_percent >= self.thresholds.memory_critical:
            alerts.append(("memory_critical", f"Memory usage critical: {resources.memory_percent:.1f}%"))
        elif resources.memory_percent >= self.thresholds.memory_warning:
            alerts.append(("memory_warning", f"Memory usage high: {resources.memory_percent:.1f}%"))
        
        # Check disk usage
        if resources.disk_usage_percent >= self.thresholds.disk_critical:
            alerts.append(("disk_critical", f"Disk usage critical: {resources.disk_usage_percent:.1f}%"))
        elif resources.disk_usage_percent >= self.thresholds.disk_warning:
            alerts.append(("disk_warning", f"Disk usage high: {resources.disk_usage_percent:.1f}%"))
        
        # Trigger alerts with cooldown
        for alert_type, message in alerts:
            await self._trigger_alert(alert_type, message, resources)
    
    async def _trigger_alert(self, alert_type: str, message: str, resources: SystemResources):
        """Trigger an alert with cooldown logic"""
        
        now = datetime.now()
        last_alert = self.last_alert_time.get(alert_type)
        
        # Check cooldown
        if last_alert and (now - last_alert) < self.alert_cooldown:
            return
        
        # Update last alert time
        self.last_alert_time[alert_type] = now
        
        # Log alert
        logger.warning(f"Resource alert: {message}")
        
        # Trigger callbacks
        for callback in self.alert_callbacks:
            try:
                await callback(alert_type, message, resources)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
    
    def add_alert_callback(self, callback: Callable):
        """Add a callback function for resource alerts"""
        self.alert_callbacks.append(callback)
    
    def get_current_resources(self) -> Optional[SystemResources]:
        """Get the most recent resource reading"""
        return self.resource_history[-1] if self.resource_history else None
    
    def get_resource_trend(self, minutes: int = 10) -> Dict[str, float]:
        """Get resource usage trend over the specified time period"""
        
        if not self.resource_history:
            return {}
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_resources = [r for r in self.resource_history if r.timestamp >= cutoff_time]
        
        if len(recent_resources) < 2:
            return {}
        
        # Calculate trends (positive = increasing, negative = decreasing)
        cpu_trend = recent_resources[-1].cpu_percent - recent_resources[0].cpu_percent
        memory_trend = recent_resources[-1].memory_percent - recent_resources[0].memory_percent
        
        return {
            "cpu_trend": cpu_trend,
            "memory_trend": memory_trend,
            "sample_count": len(recent_resources),
            "time_span_minutes": (recent_resources[-1].timestamp - recent_resources[0].timestamp).total_seconds() / 60
        }
    
    def can_handle_job(self, estimated_memory_mb: int, estimated_cpu_percent: float = 20) -> bool:
        """Check if system can handle a new job with given resource requirements"""
        
        current = self.get_current_resources()
        if not current:
            return True  # No data, assume we can handle it
        
        # Check if adding this job would exceed thresholds
        projected_memory = current.memory_percent + (estimated_memory_mb / (psutil.virtual_memory().total // (1024 * 1024)) * 100)
        projected_cpu = current.cpu_percent + estimated_cpu_percent
        
        # Use warning thresholds for job admission control
        memory_ok = projected_memory < self.thresholds.memory_warning
        cpu_ok = projected_cpu < self.thresholds.cpu_warning
        
        return memory_ok and cpu_ok
    
    def get_system_load_level(self) -> str:
        """Get current system load level as a string"""
        
        current = self.get_current_resources()
        if not current:
            return "unknown"
        
        # Determine load level based on CPU and memory
        max_usage = max(current.cpu_percent, current.memory_percent)
        
        if max_usage >= self.thresholds.memory_critical:
            return "critical"
        elif max_usage >= self.thresholds.memory_warning:
            return "high"
        elif max_usage >= 50:
            return "moderate"
        else:
            return "low"
```

#### 3.3 Enhanced Job Queue with Priority Scheduling

**Objective**: Implement sophisticated job queue management with priority scheduling and load balancing

**Step 3.3.1: Enhanced Job Service with Priority Queue**
```python
# Enhanced job_service.py with priority queue
import heapq
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import logging

@dataclass
class PriorityJob:
    """Job with priority for heap queue"""
    priority: int
    created_at: float
    job_id: str
    runtime_data: Optional[dict] = field(default=None)
    estimated_duration: int = field(default=60)
    estimated_memory: int = field(default=100)
    
    def __lt__(self, other):
        # Higher priority numbers come first, then older jobs
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.created_at < other.created_at

class EnhancedJobService:
    """Enhanced job service with priority scheduling and resource awareness"""
    
    def __init__(self):
        # Priority queue (heapq)
        self.job_queue: List[PriorityJob] = []
        self.running_jobs: Dict[str, asyncio.Task] = {}
        
        # Resource management
        self.max_concurrent_jobs = 3
        self.resource_monitor: Optional[ResourceMonitor] = None
        self.smart_batching: Optional[SmartBatchingService] = None
        
        # Queue management
        self.queue_processor_task: Optional[asyncio.Task] = None
        self.processing_paused = False
        
        # Performance tracking
        self.job_completion_times: Dict[str, float] = {}
        self.average_completion_time = 60.0  # seconds
        
        self._start_enhanced_queue_processor()
    
    def set_resource_monitor(self, monitor: ResourceMonitor):
        """Set the resource monitor for adaptive scheduling"""
        self.resource_monitor = monitor
        # Add callback for resource alerts
        monitor.add_alert_callback(self._handle_resource_alert)
    
    def set_smart_batching(self, batching_service: SmartBatchingService):
        """Set the smart batching service"""
        self.smart_batching = batching_service
    
    async def _handle_resource_alert(self, alert_type: str, message: str, resources: SystemResources):
        """Handle resource alerts by adjusting job processing"""
        
        if "critical" in alert_type:
            # Pause new job processing
            logger.warning(f"Pausing job processing due to critical resource usage: {message}")
            self.processing_paused = True
            
            # Consider cancelling lowest priority running jobs
            await self._consider_job_cancellation(resources)
            
        elif "warning" in alert_type:
            # Reduce concurrency
            logger.info(f"Reducing job concurrency due to resource warning: {message}")
            self.max_concurrent_jobs = max(1, self.max_concurrent_jobs - 1)
    
    async def _consider_job_cancellation(self, resources: SystemResources):
        """Consider cancelling lowest priority jobs if resources are critical"""
        
        if resources.memory_percent > 95 and len(self.running_jobs) > 1:
            # Find the lowest priority running job
            # This would require tracking job priorities in running_jobs
            logger.warning("Critical memory usage - job cancellation logic would go here")
            # Implementation would cancel the lowest priority job
    
    def _start_enhanced_queue_processor(self):
        """Start the enhanced queue processor"""
        if self.queue_processor_task is None or self.queue_processor_task.done():
            self.queue_processor_task = asyncio.create_task(self._enhanced_queue_processor())
    
    async def _enhanced_queue_processor(self):
        """Enhanced queue processor with resource awareness"""
        
        while True:
            try:
                # Check if processing is paused
                if self.processing_paused:
                    await self._check_resume_conditions()
                    await asyncio.sleep(5)
                    continue
                
                # Check if we can start more jobs
                if len(self.running_jobs) >= self.max_concurrent_jobs:
                    await asyncio.sleep(2)
                    continue
                
                # Check if there are jobs in queue
                if not self.job_queue:
                    await asyncio.sleep(2)
                    continue
                
                # Get next job from priority queue
                next_job = heapq.heappop(self.job_queue)
                
                # Check if system can handle this job
                if self.resource_monitor and not self.resource_monitor.can_handle_job(
                    next_job.estimated_memory, 
                    estimated_cpu_percent=20
                ):
                    # Put job back in queue and wait
                    heapq.heappush(self.job_queue, next_job)
                    logger.info(f"Delaying job {next_job.job_id} due to resource constraints")
                    await asyncio.sleep(10)
                    continue
                
                # Start the job
                await self._start_job_immediately(next_job.job_id, next_job.runtime_data)
                
                # Brief pause between job starts
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in enhanced queue processor: {e}")
                await asyncio.sleep(5)
    
    async def _check_resume_conditions(self):
        """Check if processing can be resumed after being paused"""
        
        if not self.resource_monitor:
            self.processing_paused = False
            return
        
        current_resources = self.resource_monitor.get_current_resources()
        if not current_resources:
            return
        
        # Resume if resources are back to acceptable levels
        if (current_resources.cpu_percent < 70 and 
            current_resources.memory_percent < 80):
            logger.info("Resuming job processing - resource usage normalized")
            self.processing_paused = False
            # Restore concurrency
            self.max_concurrent_jobs = min(4, self.max_concurrent_jobs + 1)
    
    async def queue_job_with_priority(
        self, 
        job_id: str, 
        runtime_data: dict = None,
        priority: Optional[int] = None
    ) -> bool:
        """Queue a job with calculated or specified priority"""
        
        if job_id in self.running_jobs:
            logger.warning(f"Job {job_id} is already running")
            return False
        
        # Calculate priority if not specified
        if priority is None:
            priority = self._calculate_job_priority(runtime_data or {})
        
        # Estimate resource requirements
        estimated_memory, estimated_duration = self._estimate_job_requirements(runtime_data or {})
        
        # Create priority job
        priority_job = PriorityJob(
            priority=priority,
            created_at=time.time(),
            job_id=job_id,
            runtime_data=runtime_data,
            estimated_duration=estimated_duration,
            estimated_memory=estimated_memory
        )
        
        # Add to priority queue
        heapq.heappush(self.job_queue, priority_job)
        
        # Update job status
        queue_position = self._get_queue_position(priority_job)
        await self.update_job_progress(job_id, JobUpdate(
            status=JobStatus.PENDING,
            current_step=f"Queued with priority {priority} (position {queue_position})"
        ))
        
        logger.info(f"Job {job_id} queued with priority {priority} (estimated {estimated_duration}s, {estimated_memory}MB)")
        return True
    
    def _calculate_job_priority(self, job_data: dict) -> int:
        """Calculate job priority based on multiple factors"""
        
        priority = 100  # Base priority
        
        # File count factor (fewer files = higher priority)
        file_count = len(job_data.get('files', []))
        if file_count <= 2:
            priority += 20
        elif file_count <= 5:
            priority += 10
        
        # Processing mode factor
        if job_data.get('processing_mode') == 'fast':
            priority += 15
        
        # Content type factor
        if job_data.get('text_content') and not job_data.get('files'):
            priority += 25  # Text-only jobs are fastest
        
        # URL processing gets medium priority
        if job_data.get('urls') and not job_data.get('files'):
            priority += 10
        
        # Time-based priority boost (older jobs get slight boost)
        # This would be implemented based on job creation time
        
        # User tier priority (if implemented)
        # Premium users could get priority boost
        
        return priority
    
    def _estimate_job_requirements(self, job_data: dict) -> Tuple[int, int]:
        """Estimate memory and duration requirements for a job"""
        
        # Base requirements
        estimated_memory = 100  # MB
        estimated_duration = 30  # seconds
        
        # File-based estimation
        files = job_data.get('files', [])
        if files:
            if self.smart_batching:
                # Use smart batching service for accurate estimates
                total_memory = 0
                total_duration = 0
                for file_data in files:
                    # Create mock file object for analysis
                    mock_file = type('MockFile', (), {
                        'filename': file_data.get('filename', 'unknown'),
                        'content_type': file_data.get('content_type', 'unknown'),
                        'size': file_data.get('size', 1024*1024)
                    })()
                    
                    analysis = self.smart_batching.analyze_file(mock_file)
                    total_memory += analysis.estimated_memory_mb
                    total_duration += analysis.estimated_processing_time
                
                estimated_memory = min(total_memory, 1500)  # Cap at 1.5GB
                estimated_duration = min(total_duration, 900)  # Cap at 15 minutes
            else:
                # Simple estimation
                estimated_memory = min(len(files) * 150, 1200)
                estimated_duration = min(len(files) * 45, 600)
        
        # URL-based estimation
        urls = job_data.get('urls', [])
        if urls:
            estimated_memory += len(urls) * 50
            estimated_duration += len(urls) * 20
        
        # Text content estimation
        if job_data.get('text_content'):
            text_length = len(job_data['text_content'])
            estimated_memory += max(20, text_length // 10000)  # 1MB per 10k chars
            estimated_duration += max(5, text_length // 5000)   # 1s per 5k chars
        
        return estimated_memory, estimated_duration
    
    def _get_queue_position(self, target_job: PriorityJob) -> int:
        """Get the position of a job in the queue"""
        
        # Count jobs with higher or equal priority that were queued earlier
        position = 1
        for job in self.job_queue:
            if (job.priority > target_job.priority or 
                (job.priority == target_job.priority and job.created_at < target_job.created_at)):
                position += 1
        
        return position
    
    def get_enhanced_queue_status(self) -> dict:
        """Get detailed queue status with priority information"""
        
        # Sort queue by priority for display
        sorted_queue = sorted(self.job_queue, key=lambda j: (-j.priority, j.created_at))
        
        queue_details = []
        for i, job in enumerate(sorted_queue[:10]):  # Show top 10
            queue_details.append({
                "position": i + 1,
                "job_id": job.job_id,
                "priority": job.priority,
                "estimated_duration": job.estimated_duration,
                "estimated_memory": job.estimated_memory,
                "queued_for_seconds": time.time() - job.created_at
            })
        
        return {
            "running_jobs": len(self.running_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "queued_jobs": len(self.job_queue),
            "processing_paused": self.processing_paused,
            "queue_details": queue_details,
            "system_load": self.resource_monitor.get_system_load_level() if self.resource_monitor else "unknown",
            "average_completion_time": self.average_completion_time
        }
```

## Success Metrics

### Performance Targets:
- **File Limit**: Max 10 files per upload (Phase 1)
- **Concurrency**: Max 3 concurrent processing jobs (Phase 1)
- **Memory**: No single job uses >50% system memory (Phase 2)
- **Success Rate**: >95% success rate for uploads under limits (Phase 2)

### User Experience Targets:
- **Feedback**: Clear progress indication for all uploads (Phase 1)
- **Error Messages**: Specific, actionable error messages (Phase 2)
- **Reliability**: No system crashes under normal load (Phase 1)

## Risk Assessment

### Low Risk (Phase 1):
- UI limits are non-breaking changes
- Concurrency limits provide safety net
- Batching fix improves performance immediately

### Medium Risk (Phase 2):
- Memory monitoring could introduce performance overhead
- Progressive upload changes user workflow
- Error handling changes might affect existing integrations

### High Risk (Phase 3):
- Resource monitoring could have false positives
- Advanced queuing might introduce complexity bugs
- Smart batching could confuse users

## Conclusion

The current architecture works for light usage but breaks down under load due to lack of resource management and sequential processing patterns. The proposed three-phase approach provides immediate stability improvements while building toward a more robust long-term solution.

Phase 1 changes are low-risk and provide immediate relief, while Phases 2-3 build a foundation for handling larger scale usage patterns.
