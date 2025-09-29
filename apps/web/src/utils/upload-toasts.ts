import { toast } from "sonner";
import type { ProcessingJob } from "@/hooks/use-job-tracking";

interface UploadStartedParams {
  itemCount: number;
  processingMode: string;
  sources: {
    files: number;
    urls: number;
    hasText: boolean;
  };
}

interface _ProcessingResult {
  documentsCreated: number;
  chunksCreated: number;
  duplicateSummary?: {
    total_files_checked: number;
    total_files_to_process: number;
    total_files_skipped: number;
    files_overwritten: number;
  };
  filesSkipped?: Array<any>;
  filesOverwritten?: Array<any>;
}

const TOAST_MESSAGES = {
  UPLOAD_STARTED: (count: number, mode: string, documentNames?: string) => ({
    title: `Upload started: Processing ${count} ${count === 1 ? 'item' : 'items'}`,
    description: documentNames ? 
      `${documentNames} • Using ${mode === 'fast' ? 'Standard' : 'OCR'} processing mode` :
      `Using ${mode === 'fast' ? 'Standard' : 'OCR'} processing mode`
  }),

  ALL_DUPLICATES: (count: number, documentNames?: string) => ({
    title: "All files were duplicates",
    description: documentNames ?
      `${documentNames} • Identical content already exists in this collection` :
      `${count} file${count === 1 ? '' : 's'} skipped - identical content already exists in this collection`
  }),

  PARTIAL_DUPLICATES: (created: number, skipped: number, overwritten: number, processedNames?: string, skippedNames?: string) => ({
    title: "Processing completed with duplicates",
    description: processedNames || skippedNames ?
      `${processedNames ? `Processed: ${processedNames}` : ''}${processedNames && skippedNames ? ' • ' : ''}${skippedNames ? `Skipped: ${skippedNames}` : ''}` :
      `Created ${created} documents • ${skipped} skipped as duplicates • ${overwritten} overwritten`
  }),

  SUCCESS_CLEAN: (documents: number, chunks: number, documentNames?: string) => ({
    title: "Processing completed successfully",
    description: documentNames ?
      `${documentNames} • Created ${chunks} chunk${chunks === 1 ? '' : 's'}` :
      `Created ${documents} document${documents === 1 ? '' : 's'} with ${chunks} chunk${chunks === 1 ? '' : 's'}`
  }),

  UPLOAD_FAILED: (error: string, documentNames?: string) => ({
    title: "Upload failed",
    description: documentNames ? `${documentNames} • ${error}` : error
  })
};

const getProcessingModeDisplay = (mode: string): string => {
  switch (mode) {
    case 'fast': return 'Standard';
    case 'balanced': return 'OCR';
    default: return mode;
  }
};

const getItemCountDescription = (sources: UploadStartedParams['sources']): string => {
  const parts: string[] = [];
  
  if (sources.files > 0) {
    parts.push(`${sources.files} file${sources.files === 1 ? '' : 's'}`);
  }
  if (sources.urls > 0) {
    parts.push(`${sources.urls} URL${sources.urls === 1 ? '' : 's'}`);
  }
  if (sources.hasText) {
    parts.push('text content');
  }
  
  return parts.join(', ');
};

/**
 * Extract and format document names from job data
 */
const getDocumentNames = (job: ProcessingJob): { processed: string[], skipped: string[], all: string[] } => {
  const processed: string[] = [];
  const skipped: string[] = [];
  const all: string[] = [];

  // Extract from input data
  if (job.input_data) {
    // Files
    if (job.input_data.files && Array.isArray(job.input_data.files)) {
      const fileNames = job.input_data.files.map((f: any) => f.filename || 'Unknown file');
      all.push(...fileNames);
    }
    
    // URLs
    if (job.input_data.urls && Array.isArray(job.input_data.urls)) {
      const urlNames = job.input_data.urls.map((url: string) => {
        // Extract domain or use first 30 chars
        try {
          const urlObj = new URL(url);
          return urlObj.hostname || url.substring(0, 30);
        } catch {
          return url.substring(0, 30);
        }
      });
      all.push(...urlNames);
    }
    
    // Text content
    if (job.input_data.text_content) {
      const textPreview = job.input_data.text_content.substring(0, 20).trim();
      all.push(`"${textPreview}${job.input_data.text_content.length > 20 ? '...' : ''}"`);
    }
  }

  // Extract skipped files from duplicate detection
  if (job.files_skipped && Array.isArray(job.files_skipped)) {
    const skippedNames = job.files_skipped.map((f: any) => f.filename || 'Unknown file');
    skipped.push(...skippedNames);
  }

  // Processed files are all files minus skipped files
  processed.push(...all.filter(name => !skipped.includes(name)));

  return { processed, skipped, all };
};

/**
 * Truncate filename for display
 */
const truncateFilename = (filename: string, maxLength: number = 25): string => {
  if (filename.length <= maxLength) return filename;
  
  // Try to preserve file extension
  const lastDotIndex = filename.lastIndexOf('.');
  if (lastDotIndex > 0 && filename.length - lastDotIndex <= 5) {
    const extension = filename.substring(lastDotIndex);
    const nameWithoutExt = filename.substring(0, lastDotIndex);
    const availableLength = maxLength - extension.length - 3; // 3 for "..."
    
    if (availableLength > 5) {
      return `${nameWithoutExt.substring(0, availableLength)}...${extension}`;
    }
  }
  
  return `${filename.substring(0, maxLength - 3)}...`;
};

/**
 * Format a list of document names for display
 */
const formatDocumentList = (names: string[], maxDisplay: number = 2): string => {
  if (names.length === 0) return '';
  
  const truncatedNames = names.slice(0, maxDisplay).map(name => truncateFilename(name));
  
  if (names.length <= maxDisplay) {
    return truncatedNames.join(', ');
  } else {
    const remaining = names.length - maxDisplay;
    return `${truncatedNames.join(', ')} and ${remaining} more`;
  }
};

export const uploadToasts = {
  /**
   * Show upload started notification with parallel processing info
   */
  started: (params: UploadStartedParams & { parallelProcessing?: boolean }) => {
    const itemDescription = getItemCountDescription(params.sources);
    const modeDisplay = getProcessingModeDisplay(params.processingMode);
    
    let description = `Using ${modeDisplay} processing mode`;
    if (params.parallelProcessing && params.sources.files > 1) {
      description += ' • Parallel processing enabled';
    }
    
    toast(`Upload started: Processing ${itemDescription}`, {
      description,
      id: 'upload-progress', // Use consistent ID for potential updates
      duration: 3000,
      icon: params.parallelProcessing && params.sources.files > 1 ? '🚀' : '⏳' // Loading icon that will show with close button
    });
  },

  /**
   * Show job queued notification
   */
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
  
  /**
   * Show system busy notification
   */
  systemBusy: (activeJobs: number, maxJobs: number) => {
    toast.warning("System busy", {
      description: `${activeJobs} of ${maxJobs} processing slots in use. Your upload will start automatically when a slot becomes available.`,
      duration: 10000
    });
  },

  /**
   * Show processing completion notification based on results
   */
  completed: (job: ProcessingJob, onViewDetails?: () => void) => {
    // Dismiss any existing upload progress toast
    toast.dismiss('upload-progress');
    
    const { documents_processed, chunks_created, duplicate_summary, files_skipped: _files_skipped, files_overwritten: _files_overwritten } = job;
    
    // Extract document names for better user feedback
    const documentNames = getDocumentNames(job);
    const processedList = formatDocumentList(documentNames.processed, 2);
    const skippedList = formatDocumentList(documentNames.skipped, 2);
    const allList = formatDocumentList(documentNames.all, 2);
    
    // Determine the scenario with improved detection
    const totalSkipped = duplicate_summary?.total_files_skipped || 0;
    const totalOverwritten = duplicate_summary?.files_overwritten || 0;
    const totalChecked = duplicate_summary?.total_files_checked || 0;
    const hasDuplicates = totalSkipped > 0 || totalOverwritten > 0;
    
    // Enhanced duplicate detection: also check if no documents/chunks were created
    // This catches cases where duplicate detection data isn't properly populated
    const noContentCreated = documents_processed === 0 && chunks_created === 0;
    const likelyDuplicate = noContentCreated && job.status === 'completed';
    
    if (hasDuplicates && documents_processed === 0) {
      // All files were duplicates (with proper duplicate_summary data)
      const count = totalChecked > 0 ? totalChecked : 1; // Fallback to 1 if no count available
      const message = TOAST_MESSAGES.ALL_DUPLICATES(count, skippedList || allList);
      toast.info(message.title, {
        description: message.description,
        action: onViewDetails ? {
          label: 'View Details',
          onClick: onViewDetails
        } : undefined,
        duration: Infinity // Manual dismiss
      });
    } else if (hasDuplicates) {
      // Some duplicates found (mixed scenario)
      const message = TOAST_MESSAGES.PARTIAL_DUPLICATES(documents_processed, totalSkipped, totalOverwritten, processedList, skippedList);
      toast.warning(message.title, {
        description: message.description,
        action: onViewDetails ? {
          label: 'View Details',
          onClick: onViewDetails
        } : undefined,
        duration: Infinity // Manual dismiss for complex scenarios
      });
    } else if (likelyDuplicate) {
      // Fallback detection: completed job with no content created
      toast.info("No new content added", {
        description: allList ? 
          `${allList} • File appears to be a duplicate or contains no processable content` :
          "File appears to be a duplicate or contains no processable content",
        duration: 8000 // Longer duration for important info
      });
    } else if (documents_processed > 0 || chunks_created > 0) {
      // Clean success - content was actually created
      const message = TOAST_MESSAGES.SUCCESS_CLEAN(documents_processed, chunks_created, processedList || allList);
      toast.success(message.title, {
        description: message.description,
        duration: 5000 // Auto-dismiss after 5s
      });
    } else {
      // Edge case: completed but unclear what happened
      toast.warning("Processing completed", {
        description: allList ?
          `${allList} • No new documents were created. Check if content already exists or if there was an issue.` :
          "No new documents were created. Check if content already exists or if there was an issue.",
        duration: 8000
      });
    }
  },

  /**
   * Show upload failure notification
   */
  failed: (error: Error | string, job?: ProcessingJob) => {
    // Dismiss any existing upload progress toast
    toast.dismiss('upload-progress');
    
    const errorMessage = error instanceof Error ? error.message : error;
    
    // Extract document names if job is provided
    let documentNames = '';
    if (job) {
      const names = getDocumentNames(job);
      documentNames = formatDocumentList(names.all, 2);
    }
    
    const message = TOAST_MESSAGES.UPLOAD_FAILED(errorMessage, documentNames);
    
    toast.error(message.title, {
      description: message.description,
      duration: Infinity // Manual dismiss for errors
    });
  },

  /**
   * Dismiss any upload-related toasts
   */
  dismiss: () => {
    toast.dismiss('upload-progress');
  }
};

export default uploadToasts; 