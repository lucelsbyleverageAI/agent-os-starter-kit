"use client";

import React, { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MinimalistBadge, MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { 
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { 
  Clock, 
  CheckCircle, 
  XCircle, 
  Loader2, 
  FileText, 
  Globe, 
  Youtube, 
  Type,
  X,
  Zap,
  Scale,
  Info
} from "lucide-react";
import { ProcessingJob } from "@/hooks/use-job-tracking";
import { cn } from "@/lib/utils";
import { DuplicateDetectionDialog } from "./duplicate-detection-dialog";

interface JobProgressCardProps {
  jobs: ProcessingJob[];
  collectionId?: string;
  onCancelJob?: (jobId: string) => Promise<boolean>;
  compact?: boolean;
}

// Helper functions
const getJobTypeIcon = (jobType: string) => {
  switch (jobType) {
    case 'youtube_processing': return Youtube;
    case 'url_processing': return Globe;
    case 'text_processing': return Type;
    default: return FileText;
  }
};

const getProcessingModeIcon = (mode: string) => {
  switch (mode) {
    case 'fast': return Zap;
    case 'balanced': return Scale;
    default: return Zap;
  }
};

const getProcessingModeText = (mode: string) => {
  switch (mode) {
    case 'fast': return 'Standard';
    case 'balanced': return 'OCR';
    default: return 'Standard';
  }
};

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'pending': return Clock;
    case 'processing': return Loader2;
    case 'completed': return CheckCircle;
    case 'failed': return XCircle;
    case 'cancelled': return XCircle;
    default: return Clock;
  }
};

// Format file size helper
const formatFileSize = (sizeInBytes: number): string => {
  if (sizeInBytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(sizeInBytes) / Math.log(k));
  return `${parseFloat((sizeInBytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

// Calculate actual file size from job data
const getActualFileSize = (job: ProcessingJob): string => {
  const inputData = job.input_data;
  
  // Check for total_file_size (most accurate)
  if (inputData?.total_file_size && typeof inputData.total_file_size === 'number') {
    return formatFileSize(inputData.total_file_size);
  }
  
  // Check individual file sizes
  if (inputData?.files && Array.isArray(inputData.files)) {
    const totalSize = inputData.files.reduce((sum: number, file: any) => {
      const fileSize = file.size || 0;
      return sum + (typeof fileSize === 'number' ? fileSize : 0);
    }, 0);
    
    if (totalSize > 0) {
      return formatFileSize(totalSize);
    }
  }
  
  // Fallback to job type-based estimation for non-file jobs
  if (job.job_type === 'youtube_processing') {
    return '~15 MB';
  } else if (job.job_type === 'url_processing') {
    return '~1 MB';
  } else if (job.job_type === 'text_processing') {
    return '< 1 KB';
  }
  
  // Default fallback for document processing when no size data available
  return 'Unknown size';
};

// Truncate title helper
const truncateTitle = (title: string, maxLength: number = 50): { truncated: string; isTruncated: boolean } => {
  if (title.length <= maxLength) {
    return { truncated: title, isTruncated: false };
  }
  return { truncated: `${title.substring(0, maxLength)}...`, isTruncated: true };
};

export const JobProgressCard = React.memo(function JobProgressCard({
  jobs,
  collectionId,
  onCancelJob,
  compact = false
}: JobProgressCardProps) {
  // Memoize filtered jobs to prevent unnecessary recalculations
  const filteredJobs = useMemo(() =>
    collectionId
      ? jobs.filter(job => job.collection_id === collectionId)
      : jobs,
    [jobs, collectionId]
  );

  // Memoize active jobs calculation
  const activeJobs = useMemo(() =>
    filteredJobs.filter(job =>
      ['pending', 'processing'].includes(job.status)
    ),
    [filteredJobs]
  );

  // Don't render the component if there are no active jobs
  if (activeJobs.length === 0) {
    return null;
  }

  return (
    <TooltipProvider>
      <Card className="w-full">
        <CardHeader className="pb-1">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              Processing Jobs
              <MinimalistBadgeWithText
                icon={Loader2}
                text={`${activeJobs.length} active`}
                tooltip={`${activeJobs.length} job${activeJobs.length === 1 ? '' : 's'} currently processing`}
              />
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {/* Only Active Jobs */}
          {activeJobs.map((job) => (
            <JobProgressItem
              key={job.id}
              job={job}
              compact={compact}
              onCancelJob={onCancelJob}
            />
          ))}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
});

// Individual Job Progress Item
interface JobProgressItemProps {
  job: ProcessingJob;
  compact?: boolean;
  onCancelJob?: (jobId: string) => Promise<boolean>;
}

const JobProgressItem = React.memo(function JobProgressItem({ job, compact = false, onCancelJob }: JobProgressItemProps) {
  const JobTypeIcon = getJobTypeIcon(job.job_type);
  const ProcessingModeIcon = getProcessingModeIcon(job.processing_mode);
  const StatusIcon = getStatusIcon(job.status);
  const isActive = ['pending', 'processing'].includes(job.status);
  const processingModeText = getProcessingModeText(job.processing_mode);
  
  // State for cancel button loading
  const [isCancelling, setIsCancelling] = React.useState(false);
  
  // State for duplicate detection dialog
  const [showDuplicateDialog, setShowDuplicateDialog] = React.useState(false);

  // Truncate title
  const { truncated: displayTitle, isTruncated } = truncateTitle(job.title);

  // Get actual file size from job data
  const actualSize = getActualFileSize(job);

  return (
    <Card className={cn(
      "transition-all hover:shadow-sm !py-1",
      isActive ? 'border-primary/30' : 'border-border'
    )}>
      <CardContent className="!px-3 !py-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 flex-1 min-w-0">
            {/* Job Type Icon */}
            <div className="flex-shrink-0">
              <MinimalistBadge 
                icon={JobTypeIcon}
                tooltip={`${job.job_type.replace('_', ' ')} job`}
              />
            </div>

            {/* Job Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2">
                {isTruncated ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <p className="font-medium text-sm text-foreground truncate cursor-help">
                        {displayTitle}
                      </p>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="max-w-xs break-words">{job.title}</p>
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <p className="font-medium text-sm text-foreground truncate">
                    {displayTitle}
                  </p>
                )}
                
                {/* Processing Mode Badge */}
                <div className="flex items-center">
                  <MinimalistBadgeWithText
                    icon={ProcessingModeIcon}
                    text={processingModeText}
                    tooltip={`Processing mode: ${processingModeText}`}
                  />
                </div>
                
                {/* File Size Badge */}
                <div className="flex items-center">
                  <span className="inline-flex items-center h-6 px-2 rounded-md bg-muted/50 text-muted-foreground/70 text-xs font-medium">
                    {actualSize}
                  </span>
                </div>

                {/* Completed Status Badge */}
                {job.status === 'completed' && (
                  <MinimalistBadge 
                    icon={CheckCircle}
                    tooltip="Completed successfully"
                    className="h-4 w-4 text-green-600"
                  />
                )}
                {job.status === 'failed' && (
                  <MinimalistBadge 
                    icon={XCircle}
                    tooltip="Processing failed"
                    className="h-4 w-4 text-red-600"
                  />
                )}
              </div>
              
              {/* Current Step for Active Jobs */}
              {isActive && job.current_step && (
                <p className="text-xs text-muted-foreground">
                  {job.current_step}
                </p>
              )}
              
              {/* Error Message */}
              {job.status === 'failed' && job.error_message && (
                <p className="text-xs text-red-600 truncate">
                  Error: {job.error_message}
                </p>
              )}

              {/* Success Summary */}
              {job.status === 'completed' && job.documents_processed > 0 && (
                <p className="text-xs text-green-700">
                  ✓ Created {job.documents_processed} document{job.documents_processed === 1 ? '' : 's'} 
                  with {job.chunks_created} chunk{job.chunks_created === 1 ? '' : 's'}
                </p>
              )}
              
              {/* Duplicate Detection Summary */}
              {job.status === 'completed' && job.duplicate_summary && (
                <div className="text-xs text-muted-foreground space-y-1">
                  <div 
                    className="cursor-pointer hover:bg-muted/30 p-1 rounded transition-colors"
                    onClick={() => setShowDuplicateDialog(true)}
                  >
                    {job.duplicate_summary.total_files_skipped > 0 && (
                      <p className="text-orange-600 flex items-center gap-1">
                        ⚠ {job.duplicate_summary.total_files_skipped} file{job.duplicate_summary.total_files_skipped === 1 ? '' : 's'} skipped as duplicate{job.duplicate_summary.total_files_skipped === 1 ? '' : 's'}
                        <Info className="h-3 w-3 ml-1" />
                      </p>
                    )}
                    {job.duplicate_summary.files_overwritten > 0 && (
                      <p className="text-blue-600 flex items-center gap-1">
                        🔄 {job.duplicate_summary.files_overwritten} file{job.duplicate_summary.files_overwritten === 1 ? '' : 's'} overwritten
                        <Info className="h-3 w-3 ml-1" />
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Side - Loading Spinner for Active Jobs or Remove Button for Completed */}
          <div className="flex-shrink-0 ml-2 flex items-center">
            {isActive && (
              <div className="flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "inline-flex items-center justify-center h-6 w-6 rounded-md bg-muted/30 text-muted-foreground",
                        "h-5 w-5",
                        job.status === 'processing' && "animate-spin text-primary"
                      )}
                    >
                      <StatusIcon className="h-4 w-4" />
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{job.status === 'processing' ? 'Currently processing' : 'Pending'}</p>
                  </TooltipContent>
                </Tooltip>
                {onCancelJob && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          "inline-flex items-center justify-center h-6 w-6 rounded-md bg-muted/50 cursor-pointer transition-colors",
                          isCancelling
                            ? "text-primary pointer-events-none"
                            : "text-muted-foreground/70 hover:text-red-600 hover:bg-red-50"
                        )}
                        onClick={async () => {
                          if (isCancelling) return;
                          setIsCancelling(true);
                          try {
                            await onCancelJob(job.id);
                          } finally {
                            setIsCancelling(false);
                          }
                        }}
                      >
                        {isCancelling ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <X className="h-4 w-4" />
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Cancel Job</p>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            )}
            {!isActive && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {/* Handle removal if needed */}}
                className="h-8 w-8 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
                title="Remove from list"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        
        {/* Duplicate Detection Dialog */}
        <DuplicateDetectionDialog
          job={job}
          open={showDuplicateDialog}
          onOpenChange={setShowDuplicateDialog}
        />
      </CardContent>
    </Card>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function - only re-render when these specific fields change
  const prevJob = prevProps.job;
  const nextJob = nextProps.job;

  // Return true if props are equal (prevent re-render), false if different (allow re-render)
  return (
    prevJob.id === nextJob.id &&
    prevJob.status === nextJob.status &&
    prevJob.title === nextJob.title &&
    prevJob.current_step === nextJob.current_step &&
    prevJob.documents_processed === nextJob.documents_processed &&
    prevJob.chunks_created === nextJob.chunks_created &&
    prevJob.error_message === nextJob.error_message &&
    prevJob.processing_mode === nextJob.processing_mode &&
    prevJob.job_type === nextJob.job_type &&
    prevJob.duplicate_summary?.total_files_skipped === nextJob.duplicate_summary?.total_files_skipped &&
    prevJob.duplicate_summary?.files_overwritten === nextJob.duplicate_summary?.files_overwritten &&
    prevProps.compact === nextProps.compact &&
    prevProps.onCancelJob === nextProps.onCancelJob
  );
}); 