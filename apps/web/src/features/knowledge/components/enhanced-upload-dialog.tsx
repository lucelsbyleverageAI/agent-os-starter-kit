"use client";

import React, { useState, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { 
  Upload, 
  Link, 
  Type, 
  Zap, 
  ScanText,
} from "lucide-react";
import { uploadToasts } from "@/utils/upload-toasts";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { UPLOAD_LIMITS } from "../constants/upload-limits";

import { FileUploadSection } from "./file-upload-section";
import { URLUploadSection } from "./url-upload-section";  
import { TextUploadSection } from "./text-upload-section";

export type ProcessingMode = 'fast' | 'balanced';

interface ProcessingModeConfig {
  id: ProcessingMode;
  name: string;
  description: string;
  detail: string;
  icon: React.ComponentType<any>;
}

const PROCESSING_MODES: ProcessingModeConfig[] = [
  {
    id: 'fast',
    name: 'Standard Processing',
    description: 'Quick text extraction with table detection',
    detail: 'Best for digital documents with selectable text',
    icon: Zap,
  },
  {
    id: 'balanced',
    name: 'OCR Processing',
    description: 'Text extraction with OCR for scanned documents',
    detail: 'Detects text from images and scanned pages (takes longer)',
    icon: ScanText,
  }
];

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
}

export function EnhancedUploadDialog({ 
  open, 
  onOpenChange, 
  onSubmit,
  collectionId 
}: EnhancedUploadDialogProps) {
  const [activeTab, setActiveTab] = useState<'files' | 'urls' | 'text'>('files');
  const [processingMode, setProcessingMode] = useState<ProcessingMode>('balanced');
  const [submitting, setSubmitting] = useState(false);
  
  // Content state
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setURLs] = useState<URLItem[]>([]);
  const [textContent, setTextContent] = useState('');

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
    setProcessingMode('balanced');
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
        processingMode
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
  }, [files, urls, textContent, processingMode, isValidForSubmission, totalItems, onSubmit, resetForm, onOpenChange]);

  // Handle dialog close
  const handleClose = useCallback(() => {
    if (submitting) return;
    onOpenChange(false);
  }, [submitting, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className={cn("!max-w-5xl !w-[80vw] max-h-[90vh]", ...getScrollbarClasses('y'))}>
        <DialogHeader>
          <DialogTitle>Upload Documents</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Processing Mode Selection */}
          <div className="space-y-3">
            <Label className="text-base font-medium">Processing Mode</Label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {PROCESSING_MODES.map((mode) => {
                const Icon = mode.icon;
                const isSelected = processingMode === mode.id;
                
                return (
                  <div 
                    key={mode.id}
                    className={cn(
                      "cursor-pointer transition-all duration-300 ease-out rounded-lg border bg-card text-card-foreground shadow-sm p-4",
                      isSelected 
                        ? "border-primary border-2 shadow-lg shadow-primary/10" 
                        : "hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10"
                    )}
                    onClick={() => setProcessingMode(mode.id)}
                  >
                    <div className="flex items-start space-x-3">
                      <Icon className="h-6 w-6 text-foreground flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-base text-foreground mb-1">{mode.name}</h3>
                        <p className="text-sm text-muted-foreground mb-2">{mode.description}</p>
                        <p className="text-xs text-muted-foreground">{mode.detail}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Content Upload Tabs */}
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)}>
            <TabsList className="grid w-full grid-cols-3">
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

            <TabsContent value="files" className="space-y-4">
              <FileUploadSection 
                files={files}
                onFilesChange={setFiles}
              />
            </TabsContent>

            <TabsContent value="urls" className="space-y-4">
              <URLUploadSection 
                urls={urls}
                onURLsChange={setURLs}
              />
            </TabsContent>

            <TabsContent value="text" className="space-y-4">
              <TextUploadSection 
                textContent={textContent}
                onTextChange={setTextContent}
              />
            </TabsContent>
          </Tabs>


        </div>

        <DialogFooter className="flex items-center justify-between">
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
} 