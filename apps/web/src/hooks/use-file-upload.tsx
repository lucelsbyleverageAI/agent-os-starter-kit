import { useState, useRef, useEffect, ChangeEvent, useCallback } from "react";
import { toast } from "sonner";
import type { Base64ContentBlock } from "@langchain/core/messages";
import { fileToContentBlock } from "@/lib/multimodal-utils";
import { useAuthContext } from "@/providers/Auth";

// Maximum file size in bytes (10MB)
export const MAX_FILE_SIZE = 10 * 1024 * 1024;

// Maximum total size for all attachments in chat (50MB)
export const MAX_TOTAL_ATTACHMENTS_SIZE = 50 * 1024 * 1024;

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
    "text/markdown"
  ]
};

export interface ProcessingAttachment {
  id: string;
  file: File;
  status: 'processing' | 'success' | 'error';
  jobId?: string;
  content?: string;
  error?: string;
}

interface UseFileUploadOptions {
  initialBlocks?: Base64ContentBlock[];
}

export function useFileUpload({
  initialBlocks = [],
}: UseFileUploadOptions = {}) {
  const { session } = useAuthContext();
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

  const startJobPolling = useCallback(async (jobId: string, attachmentId: string) => {
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
            const extractedContent = jobData.result_data?.content || jobData.output_data?.content;
            
            if (!extractedContent) {
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
            
            // Create a content block for the processed document
            const newBlock: Base64ContentBlock = {
              type: "text",
              text: `<UserUploadedAttachment>
<FileType>${processedAttachment.file.type}</FileType>
<FileName>${processedAttachment.file.name}</FileName>
<Content>
${extractedContent}
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
      const formData = new FormData();
      formData.append('file', file);
      formData.append('processing_mode', 'fast');

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

      // Start polling immediately
      startJobPolling(data.job_id, attachmentId);

      // Update attachment with job ID
      setProcessingAttachments(prev => prev.map(att => {
        if (att.id === attachmentId) {
          return {
            ...att,
            jobId: data.job_id
          };
        }
        return att;
      }));

      toast.info(`Processing ${file.name}...`);
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
  }, [session?.accessToken, startJobPolling]);

  /**
   * Upload image to storage and return a content block with storage path.
   * This replaces the old base64 approach to keep messages lean.
   *
   * Images are stored per-user with timestamps (no thread association).
   */
  const uploadImageToStorage = useCallback(async (file: File): Promise<Base64ContentBlock> => {
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

    // Return a content block with storage path for message content
    // Use preview_url for immediate display in UI
    // Note: Using 'as any' because we're extending Base64ContentBlock with url support
    return {
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
        // Upload image to storage and create storage path content block
        try {
          const block = await uploadImageToStorage(file);
          setContentBlocks(prev => [...prev, block]);
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
          // Upload image to storage and create storage path content block
          try {
            const block = await uploadImageToStorage(file);
            setContentBlocks(prev => [...prev, block]);
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
    setContentBlocks((prev) => prev.filter((_, i) => i !== idx));
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
        if (file) files.push(file);
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
            const block = await uploadImageToStorage(file);
            setContentBlocks(prev => [...prev, block]);
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