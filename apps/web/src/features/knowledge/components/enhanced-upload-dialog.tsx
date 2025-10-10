"use client";

import React, { useState, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { 
  Upload, 
  Link, 
  Type,
} from "lucide-react";
import { uploadToasts } from "@/utils/upload-toasts";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { UPLOAD_LIMITS } from "../constants/upload-limits";

import { FileUploadSection } from "./file-upload-section";
import { URLUploadSection } from "./url-upload-section";  
import { TextUploadSection } from "./text-upload-section";

export type ProcessingMode = 'fast' | 'balanced';

export interface URLItem {
  id: string;
  url: string;
  isValid: boolean;
  isYouTube: boolean;
}

interface EnhancedUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: UploadData) => Promise<void>;
  collectionId: string;
}

export interface UploadData {
  files: File[];
  urls: URLItem[];
  textContent: string;
  processingMode: ProcessingMode;
  useAIMetadata: boolean;
}

export function EnhancedUploadDialog({ 
  open, 
  onOpenChange, 
  onSubmit,
  collectionId 
}: EnhancedUploadDialogProps) {
  const [activeTab, setActiveTab] = useState<'files' | 'urls' | 'text'>('files');
  const [processingMode] = useState<ProcessingMode>('fast'); // Always use 'fast' mode
  const [submitting, setSubmitting] = useState(false);

  // Content state
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setURLs] = useState<URLItem[]>([]);
  const [textContent, setTextContent] = useState('');

  // AI metadata option
  const [useAIMetadata, setUseAIMetadata] = useState(true);

  // Calculate total items for submit button
  const totalItems = files.length + urls.length + (textContent.trim() ? 1 : 0);
  const hasContent = totalItems > 0;
  
  // Basic validation (file component handles detailed validation)
  const isValidForSubmission = React.useMemo(() => {
    if (!hasContent) return false;
    
    // Basic file limits check
    if (files.length > UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD) return false;
    
    // Check total size
    const totalSizeBytes = files.reduce((sum, file) => sum + file.size, 0);
    const totalSizeMB = Math.round(totalSizeBytes / (1024 * 1024));
    if (totalSizeMB > UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB) return false;
    
    // Check individual file sizes
    const hasOversizedFile = files.some(file => {
      const fileSizeMB = Math.round(file.size / (1024 * 1024));
      return fileSizeMB > UPLOAD_LIMITS.MAX_INDIVIDUAL_FILE_SIZE_MB;
    });
    if (hasOversizedFile) return false;
    
    return true;
  }, [hasContent, files]);

  // Reset form
  const resetForm = useCallback(() => {
    setFiles([]);
    setURLs([]);
    setTextContent('');
    setUseAIMetadata(true);
    setActiveTab('files');
  }, []);

  // Handle submission
  const handleSubmit = useCallback(async () => {
    if (!isValidForSubmission) {
      // Don't show toast here - validation errors are shown in components
      return;
    }

    setSubmitting(true);
    try {
      // Show the upload started toast
      uploadToasts.started({
        itemCount: totalItems,
        processingMode,
        sources: {
          files: files.length,
          urls: urls.length,
          hasText: textContent.trim().length > 0
        }
      });

      await onSubmit({
        files,
        urls,
        textContent,
        processingMode,
        useAIMetadata
      });

      // Reset and close - completion toast will be handled by job tracking
      resetForm();
      onOpenChange(false);
    } catch (error) {
      console.error('Upload error:', error);
      uploadToasts.failed(error instanceof Error ? error : new Error('Unknown error occurred'));
    } finally {
      setSubmitting(false);
    }
  }, [files, urls, textContent, processingMode, useAIMetadata, isValidForSubmission, totalItems, onSubmit, resetForm, onOpenChange]);

  // Handle dialog close
  const handleClose = useCallback(() => {
    if (submitting) return;
    onOpenChange(false);
  }, [submitting, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className={cn("!max-w-5xl !w-[80vw] max-h-[90vh] flex flex-col gap-0", ...getScrollbarClasses('y'))}>
        <DialogHeader className="pb-4">
          <DialogTitle>Upload Documents</DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0">
          {/* Content Upload Tabs */}
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="flex flex-col h-full">
            <TabsList className="grid w-full grid-cols-3 mb-6">
              <TabsTrigger value="files" className="flex items-center space-x-2">
                <Upload className="h-4 w-4" />
                <span>Files</span>
                {files.length > 0 && (
                  <Badge variant="secondary" className="ml-1">
                    {files.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="urls" className="flex items-center space-x-2">
                <Link className="h-4 w-4" />
                <span>URLs</span>
                {urls.length > 0 && (
                  <Badge variant="secondary" className="ml-1">
                    {urls.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="text" className="flex items-center space-x-2">
                <Type className="h-4 w-4" />
                <span>Text</span>
                {textContent.trim() && (
                  <Badge variant="secondary" className="ml-1">
                    1
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="files" className="flex-1 mt-0">
              <FileUploadSection 
                files={files}
                onFilesChange={setFiles}
              />
            </TabsContent>

            <TabsContent value="urls" className="flex-1 mt-0">
              <URLUploadSection 
                urls={urls}
                onURLsChange={setURLs}
              />
            </TabsContent>

            <TabsContent value="text" className="flex-1 mt-0">
              <TextUploadSection 
                textContent={textContent}
                onTextChange={setTextContent}
              />
            </TabsContent>
          </Tabs>
        </div>

        <DialogFooter className="flex flex-col gap-4 pt-6 mt-6 border-t">
          {/* AI Metadata Option */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="use-ai-metadata"
              checked={useAIMetadata}
              onCheckedChange={(checked) => setUseAIMetadata(checked === true)}
              disabled={submitting}
            />
            <Label
              htmlFor="use-ai-metadata"
              className="text-sm font-normal cursor-pointer"
            >
              Use AI to generate document names and descriptions automatically
            </Label>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-between">
            <Button variant="outline" onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!isValidForSubmission || submitting}
              className="min-w-[140px]"
            >
              {submitting ? (
                <div className="flex items-center space-x-2">
                  <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Starting...</span>
                </div>
              ) : (
                `Start Processing ${totalItems > 0 ? `(${totalItems})` : ''}`
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
} 