import { useState, useRef, useEffect, ChangeEvent, useCallback } from "react";
import { toast } from "sonner";
import type { Base64ContentBlock } from "@langchain/core/messages";
import { fileToContentBlock } from "@/lib/multimodal-utils";
import { useAuthContext } from "@/providers/Auth";
import { useQueryState } from "nuqs";

// Maximum file size in bytes (10MB)
export const MAX_FILE_SIZE = 10 * 1024 * 1024;

// Maximum total size for all attachments in chat (50MB)
export const MAX_TOTAL_ATTACHMENTS_SIZE = 50 * 1024 * 1024;

// Maximum words to include in document preview (10,000 words ≈ 40k chars ≈ 10k tokens)
export const MAX_PREVIEW_WORDS = 10000;

/**
 * Truncates text to a maximum number of words.
 * Returns the truncated text and metadata about truncation.
 */
function truncateToWords(
  text: string,
  maxWords: number
): { text: string; truncated: boolean; totalWords: number } {
  if (!text) {
    return { text: '', truncated: false, totalWords: 0 };
  }

  const words = text.split(/\s+/).filter(w => w.length > 0);
  const totalWords = words.length;

  if (totalWords <= maxWords) {
    return { text, truncated: false, totalWords };
  }

  return {
    text: words.slice(0, maxWords).join(' '),
    truncated: true,
    totalWords
  };
}

// Expanded supported file types
export const SUPPORTED_FILE_TYPES = {
  // Images (handled synchronously)
  images: [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp"
  ],
  // Documents (handled asynchronously)
  documents: [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", // .docx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", // .pptx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", // .xlsx
    "text/plain",
    "text/markdown",
    "text/csv", // .csv
  ]
};

export interface ProcessingAttachment {
  id: string;
  file: File;
  status: 'processing' | 'success' | 'error';
  jobId?: string;
  content?: string;
  error?: string;
  storageData?: { storage_path: string; bucket: string } | null;
}

interface UseFileUploadOptions {
  initialBlocks?: Base64ContentBlock[];
}

export function useFileUpload({
  initialBlocks = [],
}: UseFileUploadOptions = {}) {
  const { session } = useAuthContext();
  const [_threadId] = useQueryState("threadId");
  const [contentBlocks, setContentBlocks] = useState<Base64ContentBlock[]>(initialBlocks);
  const [processingAttachments, setProcessingAttachments] = useState<ProcessingAttachment[]>([]);
  const dropRef = useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);
  const pollingIntervals = useRef<{ [key: string]: NodeJS.Timeout }>({});

  // Add ref to avoid stale closure issues in polling
  const processingAttachmentsRef = useRef<ProcessingAttachment[]>([]);

  // Keep ref in sync with state
  useEffect(() => {
    processingAttachmentsRef.current = processingAttachments;
  }, [processingAttachments]);

  // Cleanup polling intervals on unmount
  useEffect(() => {
    return () => {
      Object.values(pollingIntervals.current).forEach(interval => clearInterval(interval));
    };
  }, []);

  const isDuplicate = useCallback((file: File, blocks: Base64ContentBlock[]) => {
    // Check for duplicates in content blocks
    const isDuplicateInBlocks = blocks.some(
      (b) => {
        // Check for file blocks (legacy)
        if (b.type === "file" && (b as any).metadata?.filename === file.name) return true;
        // Check for image blocks
        if (b.type === "image" && (b as any).metadata?.name === file.name) return true;
        // Check for text blocks with extracted document content
        if ((b as any).type === "text" && (b as any).metadata?.filename === file.name) return true;
        return false;
      }
    );

    // Check for duplicates in processing attachments
    const isDuplicateProcessing = processingAttachments.some(
      (a) => a.file.name === file.name
    );

    return isDuplicateInBlocks || isDuplicateProcessing;
  }, [processingAttachments]);

  const isFileTypeSupported = (file: File) => {
    return [...SUPPORTED_FILE_TYPES.images, ...SUPPORTED_FILE_TYPES.documents].includes(file.type);
  };

  const isImageFile = (file: File) => {
    return SUPPORTED_FILE_TYPES.images.includes(file.type);
  };

  const isDocumentFile = (file: File) => {
    return SUPPORTED_FILE_TYPES.documents.includes(file.type);
  };

  const calculateTotalAttachmentsSize = useCallback(() => {
    // Calculate size from existing content blocks
    let totalSize = 0;

    contentBlocks.forEach(block => {
      if (block.type === "image" && block.source_type === "base64") {
        // Estimate original file size from base64 (base64 is ~33% larger)
        const base64Size = block.data.length;
        const originalSize = Math.floor(base64Size * 0.75);
        totalSize += originalSize;
      } else if (block.type === "file" && block.source_type === "base64") {
        // Estimate original file size from base64
        const base64Size = block.data.length;
        const originalSize = Math.floor(base64Size * 0.75);
        totalSize += originalSize;
      }
    });

    // Add size from processing attachments
    processingAttachments.forEach(attachment => {
      totalSize += attachment.file.size;
    });

    return totalSize;
  }, [contentBlocks, processingAttachments]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const _startJobPolling = useCallback(async (jobId: string, attachmentId: string) => {
    const pollInterval = setInterval(async () => {
      try {
        
        const response = await fetch(`/api/langconnect/jobs/${jobId}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session?.accessToken}`,
          }
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to fetch job status: ${response.status} ${errorText}`);
        }

        const jobData = await response.json();

        if (jobData.status === 'completed') {
          // Job completed successfully
          clearInterval(pollingIntervals.current[attachmentId]);
          delete pollingIntervals.current[attachmentId];

          // Get the attachment that was just processed
          const processedAttachment = processingAttachmentsRef.current.find(att => att.id === attachmentId);
          
          if (processedAttachment) {
            // Try to get content from either result_data or output_data
            const fullContent = jobData.result_data?.content || jobData.output_data?.content;

            if (!fullContent) {
              // Set error state
              setProcessingAttachments(prev => prev.map(att => {
                if (att.id === attachmentId) {
                  return {
                    ...att,
                    status: 'error',
                    error: 'No content extracted from document'
                  };
                }
                return att;
              }));
              return;
            }

            // Truncate content to prevent context window bloat
            const { text: previewText, truncated, totalWords } = truncateToWords(fullContent, MAX_PREVIEW_WORDS);
            const truncationNotice = truncated
              ? `\n\n[CONTENT TRUNCATED - ${totalWords.toLocaleString()} words total]`
              : '';
            const content = previewText + truncationNotice;

            // Create a content block for the processed document
            const newBlock: Base64ContentBlock = {
              type: "text",
              text: `<UserUploadedAttachment>
<FileType>${processedAttachment.file.type}</FileType>
<FileName>${processedAttachment.file.name}</FileName>
<Content>
${content}
</Content>
</UserUploadedAttachment>`,
              metadata: {
                filename: processedAttachment.file.name,
                mime_type: processedAttachment.file.type,
                extracted_text: true
              }
            } as any; // Cast because Base64ContentBlock type doesn't include text blocks

            setContentBlocks(prev => [...prev, newBlock]);
            
            // Remove the processing attachment
            setProcessingAttachments(prev => prev.filter(att => att.id !== attachmentId));
          }
        } else if (jobData.status === 'failed') {
          // Job failed
          clearInterval(pollingIntervals.current[attachmentId]);
          delete pollingIntervals.current[attachmentId];

          setProcessingAttachments(prev => prev.map(att => {
            if (att.id === attachmentId) {
              return {
                ...att,
                status: 'error',
                error: jobData.error_message || 'Processing failed'
              };
            }
            return att;
          }));

          toast.error(`Failed to process file`, {
            description: jobData.error_message || 'An error occurred while processing the file'
          });
        } else {
          // Status is 'pending' or 'processing' - continue polling
        }
      } catch (_error) {
        // Don't immediately fail - network issues might be temporary
        // After several consecutive failures, we could stop polling
      }
    }, 2000); // Poll every 2 seconds

    pollingIntervals.current[attachmentId] = pollInterval;
  }, [session?.accessToken]);

  /**
   * Job polling with storage path included in the final content block.
   * This creates the new XML format that includes both storage path and preview.
   */
  const startJobPollingWithStorage = useCallback(async (
    jobId: string,
    attachmentId: string,
    storageData: { storage_path: string; bucket: string } | null
  ) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`/api/langconnect/jobs/${jobId}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session?.accessToken}`,
          }
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to fetch job status: ${response.status} ${errorText}`);
        }

        const jobData = await response.json();

        if (jobData.status === 'completed') {
          // Job completed successfully
          clearInterval(pollingIntervals.current[attachmentId]);
          delete pollingIntervals.current[attachmentId];

          // Get the attachment that was just processed
          const processedAttachment = processingAttachmentsRef.current.find(att => att.id === attachmentId);

          if (processedAttachment) {
            // Try to get content from either result_data or output_data
            const fullContent = jobData.result_data?.content || jobData.output_data?.content || '';

            // Truncate content to prevent context window bloat
            const { text: previewText, truncated, totalWords } = truncateToWords(fullContent, MAX_PREVIEW_WORDS);

            // Build truncation notice if content was truncated
            const sandboxPath = `/sandbox/user_uploads/${processedAttachment.file.name}`;
            const truncationNotice = truncated
              ? `\n\n[CONTENT TRUNCATED - ${totalWords.toLocaleString()} words total. Full file available at: ${sandboxPath}]`
              : '';

            const preview = previewText + truncationNotice;

            // Create content block with new XML format including storage path
            let xmlContent: string;

            if (storageData) {
              // New format with storage path for binary access
              xmlContent = `<UserUploadedDocument hidden="true">
<FileName>${processedAttachment.file.name}</FileName>
<FileType>${processedAttachment.file.type}</FileType>
<StoragePath>${storageData.storage_path}</StoragePath>
<SandboxPath>${sandboxPath}</SandboxPath>
<Preview>
${preview || 'No preview available'}
</Preview>
</UserUploadedDocument>`;
            } else {
              // Fallback to old format if storage upload failed (no sandbox path available)
              const legacyTruncationNotice = truncated
                ? `\n\n[CONTENT TRUNCATED - ${totalWords.toLocaleString()} words total]`
                : '';
              const legacyContent = previewText + legacyTruncationNotice;

              xmlContent = `<UserUploadedAttachment>
<FileType>${processedAttachment.file.type}</FileType>
<FileName>${processedAttachment.file.name}</FileName>
<Content>
${legacyContent || 'No content extracted'}
</Content>
</UserUploadedAttachment>`;
            }

            const newBlock: Base64ContentBlock = {
              type: "text",
              text: xmlContent,
              metadata: {
                filename: processedAttachment.file.name,
                mime_type: processedAttachment.file.type,
                extracted_text: true,
                storage_path: storageData?.storage_path,
                bucket: storageData?.bucket,
                is_binary_upload: !!storageData
              }
            } as any;

            setContentBlocks(prev => [...prev, newBlock]);

            // Remove the processing attachment
            setProcessingAttachments(prev => prev.filter(att => att.id !== attachmentId));
          }
        } else if (jobData.status === 'failed') {
          // Job failed
          clearInterval(pollingIntervals.current[attachmentId]);
          delete pollingIntervals.current[attachmentId];

          setProcessingAttachments(prev => prev.map(att => {
            if (att.id === attachmentId) {
              return {
                ...att,
                status: 'error',
                error: jobData.error_message || 'Processing failed'
              };
            }
            return att;
          }));

          toast.error(`Failed to process file`, {
            description: jobData.error_message || 'An error occurred while processing the file'
          });
        }
        // Status is 'pending' or 'processing' - continue polling
      } catch (_error) {
        // Don't immediately fail - network issues might be temporary
      }
    }, 2000);

    pollingIntervals.current[attachmentId] = pollInterval;
  }, [session?.accessToken]);

  /**
   * Upload document to storage and return a content block with storage path + preview.
   * This enables agents to access the original binary file in the sandbox.
   *
   * Documents are stored per-user with timestamps (no thread association).
   * The sandbox path is included so the backend knows where to write the file.
   */
  const _uploadDocumentToStorage = useCallback(async (file: File): Promise<Base64ContentBlock> => {
    if (!session?.accessToken) {
      throw new Error("No session found");
    }

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/langconnect/storage/upload-chat-document', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to upload document' }));
      throw new Error(errorData.error || 'Failed to upload document');
    }

    const data = await response.json();

    // Return a text content block with XML metadata for the backend
    // This tells the backend where to find the file and where to put it in the sandbox
    return {
      type: "text",
      text: `<UserUploadedDocument hidden="true">
<FileName>${file.name}</FileName>
<FileType>${file.type}</FileType>
<StoragePath>${data.storage_path}</StoragePath>
<SandboxPath>/sandbox/user_uploads/${file.name}</SandboxPath>
</UserUploadedDocument>`,
      metadata: {
        filename: file.name,
        mime_type: file.type,
        storage_path: data.storage_path,
        bucket: data.bucket,
        is_binary_upload: true
      }
    } as any as Base64ContentBlock;
  }, [session?.accessToken]);

  const processDocument = useCallback(async (file: File) => {
    if (!session?.accessToken) {
      toast.error("No session found", {
        description: "Failed to process document. Please try again.",
      });
      return;
    }

    const attachmentId = crypto.randomUUID();

    // Add to processing attachments immediately
    setProcessingAttachments(prev => [...prev, {
      id: attachmentId,
      file,
      status: 'processing'
    }]);

    try {
      // Step 1: Upload binary to storage first
      const storageFormData = new FormData();
      storageFormData.append('file', file);

      const storageResponse = await fetch('/api/langconnect/storage/upload-chat-document', {
        method: 'POST',
        body: storageFormData,
      });

      let storageData: { storage_path: string; bucket: string } | null = null;
      if (storageResponse.ok) {
        storageData = await storageResponse.json();
      }

      // Step 2: Extract text preview
      // Use 'quick' mode for PDFs (fast synchronous extraction), 'fast' for other documents
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('processing_mode', isPdf ? 'quick' : 'fast');

      const response = await fetch('/api/langconnect/documents/extract/text', {
        method: 'POST',
        body: formData,
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        }
      });

      if (!response.ok) {
        throw new Error('Failed to start document processing');
      }

      const data = await response.json();

      // Check if this is a synchronous response (quick mode) or async job response
      // Sync response has 'success' field, async has 'job_id' field
      if (data.success !== undefined) {
        // Synchronous response - process immediately
        if (!data.success) {
          // Extraction failed
          setProcessingAttachments(prev => prev.map(att => {
            if (att.id === attachmentId) {
              return {
                ...att,
                status: 'error',
                error: data.error_message || 'Extraction failed'
              };
            }
            return att;
          }));
          toast.error(`Failed to process ${file.name}`, {
            description: data.error_message || 'An error occurred'
          });
          return;
        }

        // Extraction succeeded - create content block immediately
        const fullContent = data.content || '';
        const { text: previewText, truncated, totalWords } = truncateToWords(fullContent, MAX_PREVIEW_WORDS);

        const sandboxPath = `/sandbox/user_uploads/${file.name}`;
        const truncationNotice = truncated
          ? `\n\n[CONTENT TRUNCATED - ${totalWords.toLocaleString()} words total. Full file available at: ${sandboxPath}]`
          : '';
        const preview = previewText + truncationNotice;

        let xmlContent: string;
        if (storageData) {
          xmlContent = `<UserUploadedDocument hidden="true">
<FileName>${file.name}</FileName>
<FileType>${file.type}</FileType>
<StoragePath>${storageData.storage_path}</StoragePath>
<SandboxPath>${sandboxPath}</SandboxPath>
<Preview>
${preview || 'No preview available'}
</Preview>
</UserUploadedDocument>`;
        } else {
          const legacyTruncationNotice = truncated
            ? `\n\n[CONTENT TRUNCATED - ${totalWords.toLocaleString()} words total]`
            : '';
          const legacyContent = previewText + legacyTruncationNotice;

          xmlContent = `<UserUploadedAttachment>
<FileType>${file.type}</FileType>
<FileName>${file.name}</FileName>
<Content>
${legacyContent || 'No content extracted'}
</Content>
</UserUploadedAttachment>`;
        }

        const newBlock: Base64ContentBlock = {
          type: "text",
          text: xmlContent,
          metadata: {
            filename: file.name,
            mime_type: file.type,
            extracted_text: true,
            storage_path: storageData?.storage_path,
            bucket: storageData?.bucket,
            is_binary_upload: !!storageData
          }
        } as any;

        setContentBlocks(prev => [...prev, newBlock]);
        setProcessingAttachments(prev => prev.filter(att => att.id !== attachmentId));
        return;
      }

      // Async job response - update attachment and start polling
      setProcessingAttachments(prev => prev.map(att => {
        if (att.id === attachmentId) {
          return {
            ...att,
            jobId: data.job_id,
            storageData: storageData
          } as ProcessingAttachment;
        }
        return att;
      }));

      // Start polling with storage data
      startJobPollingWithStorage(data.job_id, attachmentId, storageData);
    } catch (error) {
      console.error('Error processing document:', error);

      setProcessingAttachments(prev => prev.map(att => {
        if (att.id === attachmentId) {
          return {
            ...att,
            status: 'error',
            error: error instanceof Error ? error.message : 'Failed to process document'
          };
        }
        return att;
      }));

      toast.error(`Failed to process ${file.name}`, {
        description: error instanceof Error ? error.message : 'An error occurred'
      });
    }
  }, [session?.accessToken]);

  /**
   * Upload image to storage and return content blocks with storage path.
   * Returns an array with:
   * 1. Image content block for model vision
   * 2. Text block with XML metadata for sandbox transfer
   *
   * Images are stored per-user with timestamps (no thread association).
   */
  const uploadImageToStorage = useCallback(async (file: File): Promise<Base64ContentBlock[]> => {
    if (!session?.accessToken) {
      throw new Error("No session found");
    }

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/langconnect/storage/upload-chat-image', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to upload image' }));
      throw new Error(errorData.error || 'Failed to upload image');
    }

    const data = await response.json();

    // Return array of content blocks:
    // 1. Image block for model vision capability
    // 2. Hidden text block with XML for sandbox transfer
    const imageBlock: Base64ContentBlock = {
      type: "image",
      source_type: "url",
      url: data.storage_path,  // Storage path for message content (will be converted to signed URL at runtime)
      metadata: {
        name: file.name,
        storage_path: data.storage_path,
        bucket: data.bucket,
        preview_url: data.preview_url  // Temporary signed URL for UI preview
      },
    } as any as Base64ContentBlock;

    // XML metadata block for the backend to transfer to sandbox
    const xmlBlock: Base64ContentBlock = {
      type: "text",
      text: `<UserUploadedImage hidden="true">
<FileName>${file.name}</FileName>
<FileType>${file.type}</FileType>
<StoragePath>${data.storage_path}</StoragePath>
<SandboxPath>/sandbox/user_uploads/${file.name}</SandboxPath>
</UserUploadedImage>`,
      metadata: {
        filename: file.name,
        mime_type: file.type,
        storage_path: data.storage_path,
        bucket: data.bucket,
        is_hidden_xml: true
      }
    } as any as Base64ContentBlock;

    return [imageBlock, xmlBlock];
  }, [session?.accessToken]);

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    
    const fileArray = Array.from(files);
    
    // Validate files
    const oversizedFiles = fileArray.filter(file => file.size > MAX_FILE_SIZE);
    const unsupportedFiles = fileArray.filter(file => !isFileTypeSupported(file));
    const duplicateFiles = fileArray.filter(file => isDuplicate(file, contentBlocks));
    
    // Check total size limit
    const currentTotalSize = calculateTotalAttachmentsSize();
    const newFilesSize = fileArray.reduce((sum, file) => sum + file.size, 0);
    const _wouldExceedTotalLimit = currentTotalSize + newFilesSize > MAX_TOTAL_ATTACHMENTS_SIZE;
    
    // Filter valid files (including total size check)
    let remainingBudget = MAX_TOTAL_ATTACHMENTS_SIZE - currentTotalSize;
    const validFiles = fileArray.filter(file => {
      const isValid = file.size <= MAX_FILE_SIZE && 
                     isFileTypeSupported(file) && 
                     !isDuplicate(file, contentBlocks) &&
                     file.size <= remainingBudget;
      
      if (isValid) {
        remainingBudget -= file.size;
      }
      
      return isValid;
    });
    
    // Files that would exceed total limit
    const totalLimitExceededFiles = fileArray.filter(file => 
      file.size <= MAX_FILE_SIZE && 
      isFileTypeSupported(file) && 
      !isDuplicate(file, contentBlocks) &&
      !validFiles.includes(file)
    );

    // Show appropriate error messages
    if (oversizedFiles.length > 0) {
      toast.error(
        `Files exceeding 10MB limit: ${oversizedFiles.map(f => f.name).join(", ")}`
      );
    }
    if (unsupportedFiles.length > 0) {
      toast.error(
        `Unsupported file types: ${unsupportedFiles.map(f => f.name).join(", ")}`
      );
    }
    if (duplicateFiles.length > 0) {
      toast.error(
        `Duplicate files: ${duplicateFiles.map(f => f.name).join(", ")}`
      );
    }
    if (totalLimitExceededFiles.length > 0) {
      const currentSizeFormatted = formatFileSize(currentTotalSize);
      const maxSizeFormatted = formatFileSize(MAX_TOTAL_ATTACHMENTS_SIZE);
      toast.error(
        `Total attachment limit (${maxSizeFormatted}) would be exceeded. Current: ${currentSizeFormatted}. Files not added: ${totalLimitExceededFiles.map(f => f.name).join(", ")}`
      );
    }

    // Process valid files
    for (const file of validFiles) {
      if (isImageFile(file)) {
        // Upload image to storage and create storage path content blocks
        try {
          const blocks = await uploadImageToStorage(file);
          setContentBlocks(prev => [...prev, ...blocks]);
        } catch (error) {
          console.error('Error uploading image:', error);
          toast.error(`Failed to upload ${file.name}`, {
            description: error instanceof Error ? error.message : 'An error occurred'
          });
        }
      } else if (isDocumentFile(file)) {
        // Handle documents asynchronously
        await processDocument(file);
      }
    }

    e.target.value = "";
  };

  // Drag and drop handlers
  useEffect(() => {
    if (!dropRef.current) return;

    // Global drag events with counter for robust dragOver state

    const handleWindowDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current += 1;
        setDragOver(true);
      }
    };
    const handleWindowDragLeave = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) {
          setDragOver(false);
          dragCounter.current = 0;
        }
      }
    };
    const handleWindowDrop = async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setDragOver(false);

      if (!e.dataTransfer) return;

      const files = Array.from(e.dataTransfer.files);
      
      // Validate files
      const oversizedFiles = files.filter(file => file.size > MAX_FILE_SIZE);
      const unsupportedFiles = files.filter(file => !isFileTypeSupported(file));
      const duplicateFiles = files.filter(file => isDuplicate(file, contentBlocks));
      
      // Check total size limit
      const currentTotalSize = calculateTotalAttachmentsSize();
      let remainingBudget = MAX_TOTAL_ATTACHMENTS_SIZE - currentTotalSize;
      const validFiles = files.filter(file => {
        const isValid = file.size <= MAX_FILE_SIZE && 
                       isFileTypeSupported(file) && 
                       !isDuplicate(file, contentBlocks) &&
                       file.size <= remainingBudget;
        
        if (isValid) {
          remainingBudget -= file.size;
        }
        
        return isValid;
      });
      
      // Files that would exceed total limit
      const totalLimitExceededFiles = files.filter(file => 
        file.size <= MAX_FILE_SIZE && 
        isFileTypeSupported(file) && 
        !isDuplicate(file, contentBlocks) &&
        !validFiles.includes(file)
      );

      // Show appropriate error messages
      if (oversizedFiles.length > 0) {
        toast.error(
          `Files exceeding 10MB limit: ${oversizedFiles.map(f => f.name).join(", ")}`
        );
      }
      if (unsupportedFiles.length > 0) {
        toast.error(
          `Unsupported file types: ${unsupportedFiles.map(f => f.name).join(", ")}`
        );
      }
      if (duplicateFiles.length > 0) {
        toast.error(
          `Duplicate files: ${duplicateFiles.map(f => f.name).join(", ")}`
        );
      }
      if (totalLimitExceededFiles.length > 0) {
        const currentSizeFormatted = formatFileSize(currentTotalSize);
        const maxSizeFormatted = formatFileSize(MAX_TOTAL_ATTACHMENTS_SIZE);
        toast.error(
          `Total attachment limit (${maxSizeFormatted}) would be exceeded. Current: ${currentSizeFormatted}. Files not added: ${totalLimitExceededFiles.map(f => f.name).join(", ")}`
        );
      }

      // Process valid files
      for (const file of validFiles) {
        if (isImageFile(file)) {
          // Upload image to storage and create storage path content blocks
          try {
            const blocks = await uploadImageToStorage(file);
            setContentBlocks(prev => [...prev, ...blocks]);
          } catch (error) {
            console.error('Error uploading image:', error);
            toast.error(`Failed to upload ${file.name}`, {
              description: error instanceof Error ? error.message : 'An error occurred'
            });
          }
        } else if (isDocumentFile(file)) {
          // Handle documents asynchronously
          await processDocument(file);
        }
      }
    };
    const handleWindowDragEnd = (e: DragEvent) => {
      dragCounter.current = 0;
      setDragOver(false);
    };
    window.addEventListener("dragenter", handleWindowDragEnter);
    window.addEventListener("dragleave", handleWindowDragLeave);
    window.addEventListener("drop", handleWindowDrop);
    window.addEventListener("dragend", handleWindowDragEnd);

    // Prevent default browser behavior for dragover globally
    const handleWindowDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("dragover", handleWindowDragOver);
    // Remove element-specific drop event (handled globally)
    const handleDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(true);
    };
    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const element = dropRef.current;
    element.addEventListener("dragover", handleDragOver);
    element.addEventListener("dragenter", handleDragEnter);
    element.addEventListener("dragleave", handleDragLeave);

    return () => {
      element.removeEventListener("dragover", handleDragOver);
      element.removeEventListener("dragenter", handleDragEnter);
      element.removeEventListener("dragleave", handleDragLeave);
      window.removeEventListener("dragenter", handleWindowDragEnter);
      window.removeEventListener("dragleave", handleWindowDragLeave);
      window.removeEventListener("drop", handleWindowDrop);
      window.removeEventListener("dragend", handleWindowDragEnd);
      window.removeEventListener("dragover", handleWindowDragOver);
      dragCounter.current = 0;
    };
  }, [contentBlocks, calculateTotalAttachmentsSize, isDuplicate, processDocument, uploadImageToStorage]);

  const removeBlock = (idx: number) => {
    setContentBlocks((prev) => {
      const blockToRemove = prev[idx];

      // If removing an image block, also remove associated hidden XML block
      if (blockToRemove?.type === "image") {
        const imageName = (blockToRemove as any).metadata?.name;
        if (imageName) {
          // Filter out both the image and its associated hidden XML block
          return prev.filter((block, i) => {
            if (i === idx) return false; // Remove the clicked block
            // Also remove hidden XML block with matching filename
            if ((block as any).metadata?.is_hidden_xml &&
                (block as any).metadata?.filename === imageName) {
              return false;
            }
            return true;
          });
        }
      }

      // Default: just remove the single block
      return prev.filter((_, i) => i !== idx);
    });
  };

  const removeProcessingAttachment = (id: string) => {
    // Clear polling interval if exists
    if (pollingIntervals.current[id]) {
      clearInterval(pollingIntervals.current[id]);
      delete pollingIntervals.current[id];
    }
    
    setProcessingAttachments(prev => prev.filter(att => att.id !== id));
  };

  const resetBlocks = () => {
    setContentBlocks([]);
    // Clear all polling intervals
    Object.values(pollingIntervals.current).forEach(interval => clearInterval(interval));
    pollingIntervals.current = {};
    setProcessingAttachments([]);
  };

  /**
   * Handle paste event for files (images, PDFs)
   * Can be used as onPaste={handlePaste} on a textarea or input
   */
  const handlePaste = async (
    e: React.ClipboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    const items = e.clipboardData.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) {
          // Add timestamp suffix to pasted images to prevent false duplicate detection
          // Browsers often name pasted images "image.png" by default
          if (file.name === "image.png" || file.name === "image.jpg" || file.name === "image.jpeg") {
            const timestamp = Date.now();
            const extension = file.name.split('.').pop();
            const newName = `pasted-image-${timestamp}.${extension}`;
            const renamedFile = new File([file], newName, { type: file.type });
            files.push(renamedFile);
          } else {
            files.push(file);
          }
        }
      }
    }
    if (files.length === 0) {
      // No files, allow default paste (text, etc)
      return;
    }
    // Files present, handle as before and prevent default
    e.preventDefault();
    const validFiles = files.filter((file) =>
      SUPPORTED_FILE_TYPES.images.includes(file.type) ||
      SUPPORTED_FILE_TYPES.documents.includes(file.type)
    );
    const invalidFiles = files.filter(
      (file) => !SUPPORTED_FILE_TYPES.images.includes(file.type) &&
                !SUPPORTED_FILE_TYPES.documents.includes(file.type)
    );
    const isDuplicate = (file: File) => {
      return contentBlocks.some((b) => {
        // Check for file blocks (legacy)
        if (b.type === "file" && (b as any).metadata?.filename === file.name) return true;
        // Check for image blocks
        if (b.type === "image" && (b as any).metadata?.name === file.name) return true;
        // Check for text blocks with extracted document content
        if ((b as any).type === "text" && (b as any).metadata?.filename === file.name) return true;
        return false;
      });
    };
    const duplicateFiles = validFiles.filter(isDuplicate);
    const uniqueFiles = validFiles.filter((file) => !isDuplicate(file));
    if (invalidFiles.length > 0) {
      toast.error(
        "You have pasted an invalid file type. Please paste a JPEG, PNG, GIF, WEBP image or a PDF.",
      );
    }
    if (duplicateFiles.length > 0) {
      toast.error(
        `Duplicate file(s) detected: ${duplicateFiles.map((f) => f.name).join(", ")}. Each file can only be uploaded once per message.`,
      );
    }
    if (uniqueFiles.length > 0) {
      // Process each file based on type
      for (const file of uniqueFiles) {
        if (isImageFile(file)) {
          // Upload image to storage
          try {
            const blocks = await uploadImageToStorage(file);
            setContentBlocks(prev => [...prev, ...blocks]);
          } catch (error) {
            console.error('Error uploading pasted image:', error);
            toast.error(`Failed to upload ${file.name}`, {
              description: error instanceof Error ? error.message : 'An error occurred'
            });
          }
        } else if (isDocumentFile(file)) {
          // Handle documents with base64 (paste doesn't support async document processing)
          const block = await fileToContentBlock(file);
          setContentBlocks(prev => [...prev, block]);
        }
      }
    }
  };

  return {
    contentBlocks,
    setContentBlocks,
    processingAttachments,
    handleFileUpload,
    dropRef,
    removeBlock,
    removeProcessingAttachment,
    resetBlocks,
    dragOver,
    handlePaste,
    calculateTotalAttachmentsSize,
    formatFileSize,
    MAX_TOTAL_ATTACHMENTS_SIZE,
  };
}