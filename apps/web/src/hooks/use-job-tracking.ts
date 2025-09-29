import { useState, useEffect, useCallback } from 'react';
import { useAuthContext } from '@/providers/Auth';
import { toast } from 'sonner';
import { uploadToasts } from '@/utils/upload-toasts';

export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type JobType = 'document_processing' | 'youtube_processing' | 'url_processing' | 'text_processing';

export interface ProcessingJob {
  id: string;
  status: JobStatus;
  progress_percentage: number;
  title: string;
  description?: string;
  collection_id: string;
  job_type: JobType;
  created_at: Date;
  started_at?: Date;
  completed_at?: Date;
  error_message?: string;
  current_step?: string;
  total_steps?: number;
  documents_processed: number;
  chunks_created: number;
  processing_mode: 'fast' | 'balanced' | 'enhanced';
  estimated_duration_seconds?: number;
  actual_duration_seconds?: number;
  input_data?: Record<string, any>;
  // Duplicate detection results
  duplicate_summary?: {
    total_files_checked: number;
    total_files_to_process: number;
    total_files_skipped: number;
    files_overwritten: number;
  };
  files_skipped?: Array<{
    filename: string;
    action: string;
    reason: string;
    existing_document_id?: string;
    existing_document?: {
      title: string;
      original_filename: string;
      created_at: string;
    };
    content_hash?: string;
  }>;
  files_overwritten?: Array<{
    filename: string;
    action: string;
    reason: string;
    previous_document_id?: string;
    previous_document?: {
      title: string;
      original_filename: string;
      created_at: string;
    };
    content_hash?: string;
  }>;
}

interface UseJobTrackingReturn {
  jobs: ProcessingJob[];
  loading: boolean;
  error: string | null;
  addJob: (job: ProcessingJob) => void;
  updateJobStatus: (jobId: string, updates: Partial<ProcessingJob>) => void;
  removeJob: (jobId: string) => void;
  getJobsByCollection: (collectionId: string) => ProcessingJob[];
  getActiveJobs: () => ProcessingJob[];
  clearCompletedJobs: () => void;
  refreshJobs: () => Promise<void>;
  cancelJob: (jobId: string) => Promise<boolean>;
}

interface JobTrackingOptions {
  onJobCompleted?: (job: ProcessingJob) => void;
}

// Job API calls now use the Next.js proxy route at /api/langconnect/

export function useJobTracking(options?: JobTrackingOptions): UseJobTrackingReturn {
  const { session, user, isLoading: authLoading } = useAuthContext();
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // No longer needed - using simple polling approach

  // Helper to format job from API response
  const formatJob = useCallback((apiJob: any): ProcessingJob => {
    return {
      id: apiJob.id,
      status: apiJob.status,
      progress_percentage: apiJob.progress_percentage || apiJob.progress_percent || 0,
      title: apiJob.title,
      description: apiJob.description,
      collection_id: apiJob.collection_id,
      job_type: apiJob.job_type,
      created_at: new Date(apiJob.created_at),
      started_at: apiJob.started_at ? new Date(apiJob.started_at) : undefined,
      completed_at: apiJob.completed_at ? new Date(apiJob.completed_at) : undefined,
      error_message: apiJob.error_message,
      current_step: apiJob.current_step,
      total_steps: apiJob.total_steps,
      documents_processed: apiJob.documents_processed || 0,
      chunks_created: apiJob.chunks_created || 0,
      processing_mode: apiJob.processing_options?.processing_mode || 'fast',
      estimated_duration_seconds: apiJob.estimated_duration_seconds,
      actual_duration_seconds: apiJob.actual_duration_seconds || apiJob.processing_time_seconds,
      input_data: apiJob.input_data,
      // Duplicate detection results from output_data
      duplicate_summary: apiJob.output_data?.duplicate_summary,
      files_skipped: apiJob.output_data?.files_skipped,
      files_overwritten: apiJob.output_data?.files_overwritten,
    };
  }, []);

  // Fetch jobs from API
  const fetchJobs = useCallback(async (): Promise<ProcessingJob[]> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }

    const url = new URL('/api/langconnect/jobs', window.location.origin);
    url.searchParams.set('limit', '50'); // Get more jobs for better UX

    const response = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch jobs: ${response.statusText}`);
    }

    const data = await response.json();
    return data.jobs.map(formatJob);
  }, [session?.accessToken, formatJob]);

  // Refresh jobs function
  const refreshJobs = useCallback(async () => {
    // Wait for auth to be fully loaded and ensure we have a valid session
    if (authLoading || !session?.accessToken || !user?.id) return;

    setLoading(true);
    setError(null);

    try {
      const fetchedJobs = await fetchJobs();
      setJobs(fetchedJobs);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch jobs';
      setError(errorMessage);
      console.error('Error fetching jobs:', err);
      toast.error('Unable to load processing jobs', {
        description: errorMessage,
      });
    } finally {
      setLoading(false);
    }
  }, [fetchJobs, authLoading, session?.accessToken, user?.id]);

  // Initial setup - fetch jobs once on mount
  useEffect(() => {
    // Only fetch jobs when auth is fully loaded and we have valid session data
    if (authLoading || !session?.accessToken || !user?.id) return;

    refreshJobs();
  }, [authLoading, session?.accessToken, user?.id, refreshJobs]);



  // Job manipulation functions
  // Targeted polling for a specific job
  const startJobPolling = useCallback((jobId: string) => {
    if (authLoading || !session?.accessToken) return;

    let pollAttempts = 0;
    const maxPollAttempts = 60; // 5 minutes max
    
    
    const poll = async () => {
      pollAttempts++;
      
      try {
        const response = await fetch(`/api/langconnect/jobs/${jobId}`, {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (response.ok) {
          const updatedJobData = await response.json();
          const updatedJob = formatJob(updatedJobData);
          
          setJobs(prev => prev.map(j => 
            j.id === jobId ? updatedJob : j
          ));

          // Check if job is complete
          if (['completed', 'failed', 'cancelled'].includes(updatedJob.status)) {
                        
            // Show completion notification
            if (updatedJob.status === 'completed') {
              uploadToasts.completed(updatedJob);
              
              // Call the completion callback if provided
              if (options?.onJobCompleted) {
                options.onJobCompleted(updatedJob);
              }
            } else if (updatedJob.status === 'failed') {
              uploadToasts.failed(updatedJob.error_message || 'Processing failed', updatedJob);
            } else if (updatedJob.status === 'cancelled') {
              toast.info(`Processing cancelled: ${updatedJob.title}`, {
                description: 'Job was cancelled by user',
              });
            }
            
            // Remove the job from state after a short delay to allow the toast to show
            setTimeout(() => {
              setJobs(prev => prev.filter(j => j.id !== jobId));
                          }, 1000);
            
            return; // Stop polling
          }
          
          // Continue polling if still active and under max attempts
          if (pollAttempts < maxPollAttempts) {
            const delay = pollAttempts < 10 ? 1000 : pollAttempts < 30 ? 2000 : 5000;
            setTimeout(poll, delay);
          } else {
            console.warn(`⏰ Polling timeout for job ${jobId} after ${maxPollAttempts} attempts`);
          }
        } else {
          console.error(`Failed to poll job ${jobId}: ${response.status}`);
        }
      } catch (error) {
        console.error(`Polling error for job ${jobId}:`, error);
      }
    };

    // Start polling immediately
    poll();
  }, [authLoading, session?.accessToken, formatJob, options]);

  const addJob = useCallback((job: ProcessingJob) => {
    setJobs(prev => {
      const exists = prev.some(existingJob => existingJob.id === job.id);
      if (exists) return prev;
      
      return [...prev, job];
    });

    // Start polling for this specific job if it's active
    if (['pending', 'processing'].includes(job.status)) {
      startJobPolling(job.id);
    }
  }, [startJobPolling]);

  const updateJobStatus = useCallback((jobId: string, updates: Partial<ProcessingJob>) => {
    setJobs(prev => prev.map(job => 
      job.id === jobId ? { ...job, ...updates } : job
    ));
  }, []);

  const removeJob = useCallback((jobId: string) => {
    setJobs(prev => prev.filter(job => job.id !== jobId));
  }, []);

  const getJobsByCollection = useCallback((collectionId: string) => {
    return jobs.filter(job => job.collection_id === collectionId);
  }, [jobs]);

  const getActiveJobs = useCallback(() => {
    return jobs.filter(job => ['pending', 'processing'].includes(job.status));
  }, [jobs]);

  const clearCompletedJobs = useCallback(() => {
    setJobs(prev => prev.filter(job => !['completed', 'failed'].includes(job.status)));
  }, []);

  // Job cancellation function
  const cancelJob = useCallback(async (jobId: string): Promise<boolean> => {
    if (authLoading || !session?.accessToken) {
      toast.error('Authentication not ready or no token available');
      return false;
    }

    try {
      const response = await fetch(`/api/langconnect/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to cancel job: ${response.statusText}`);
      }

      const result = await response.json();
      
      if (result.success) {
        // Update job status locally immediately
        setJobs(prev => prev.map(job => 
          job.id === jobId 
            ? { ...job, status: 'cancelled', current_step: 'Cancelled by user' }
            : job
        ));

        toast.success('Job cancelled successfully');
                
        // Remove the job from UI after a short delay
        setTimeout(() => {
          setJobs(prev => prev.filter(job => job.id !== jobId));
                  }, 1000);
        
        return true;
      } else {
        throw new Error('Failed to cancel job');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to cancel job';
      console.error(`❌ Error cancelling job ${jobId}:`, error);
      toast.error('Failed to cancel job', {
        description: errorMessage,
      });
      return false;
    }
  }, [authLoading, session?.accessToken]);

  return {
    jobs,
    loading,
    error,
    addJob,
    updateJobStatus,
    removeJob,
    getJobsByCollection,
    getActiveJobs,
    clearCompletedJobs,
    refreshJobs,
    cancelJob,
  };
} 