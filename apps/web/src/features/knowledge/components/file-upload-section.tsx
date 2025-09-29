"use client";

import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { 
  Upload, 
  X, 
  FileText, 
  File, 
  Video,
  FileArchive,
  FileSpreadsheet,
  AlertCircle,
  Info
} from "lucide-react";
import { 
  UPLOAD_LIMITS, 
  UPLOAD_MESSAGES, 
  formatFileSize, 
  bytesToMB 
} from "../constants/upload-limits";

interface FileUploadSectionProps {
  files: File[];
  onFilesChange: (files: File[]) => void;
}

// File type detection
const getFileIcon = (file: File) => {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();

  if (type.startsWith('video/')) return Video;
  if (type.includes('pdf')) return FileText;
  if (type.includes('word') || name.endsWith('.docx') || name.endsWith('.doc')) return FileText;
  if (type.includes('presentation') || name.endsWith('.pptx') || name.endsWith('.ppt')) return FileText;
  if (type.includes('spreadsheet') || name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv')) return FileSpreadsheet;
  if (type.includes('zip') || type.includes('archive')) return FileArchive;
  
  return File;
};

// File size formatting is now imported from upload-limits

// Validation types
interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

// File type validation
const isValidFileType = (file: File): boolean => {
  const validExtensions = [
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', 
    '.txt', '.csv', '.html', '.htm', '.md', '.markdown'
  ];

  const fileName = file.name.toLowerCase();
  return (UPLOAD_LIMITS.SUPPORTED_FILE_TYPES as readonly string[]).includes(file.type) || 
         validExtensions.some(ext => fileName.endsWith(ext));
};

// Comprehensive upload validation
const validateUploadBatch = (files: File[]): ValidationResult => {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  // Check file count
  if (files.length > UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD) {
    errors.push(UPLOAD_MESSAGES.TOO_MANY_FILES(UPLOAD_LIMITS.MAX_FILES_PER_UPLOAD));
  }
  
  // Check total size
  const totalSizeBytes = files.reduce((sum, file) => sum + file.size, 0);
  const totalSizeMB = bytesToMB(totalSizeBytes);
  if (totalSizeMB > UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB) {
    errors.push(UPLOAD_MESSAGES.TOTAL_SIZE_TOO_LARGE(totalSizeMB, UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB));
  }
  
  // Check individual file sizes and types
  files.forEach(file => {
    const fileSizeMB = bytesToMB(file.size);
    
    if (fileSizeMB > UPLOAD_LIMITS.MAX_INDIVIDUAL_FILE_SIZE_MB) {
      errors.push(UPLOAD_MESSAGES.INDIVIDUAL_FILE_TOO_LARGE(
        file.name, fileSizeMB, UPLOAD_LIMITS.MAX_INDIVIDUAL_FILE_SIZE_MB
      ));
    }
    
    if (!isValidFileType(file)) {
      errors.push(UPLOAD_MESSAGES.UNSUPPORTED_FILE_TYPE(file.name, file.type || 'unknown'));
    }
  });
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings
  };
};

export function FileUploadSection({ files, onFilesChange }: FileUploadSectionProps) {
  const [dragActive, setDragActive] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult>({ 
    isValid: true, errors: [], warnings: [] 
  });

  const addFiles = useCallback((newFiles: File[]) => {
    // Check for duplicates first
    const uniqueFiles = newFiles.filter(file => {
      const exists = files.some(existingFile => 
        existingFile.name === file.name && existingFile.size === file.size
      );
      if (exists) {
        toast.warning(`File already added: ${file.name}`);
        return false;
      }
      return true;
    });

    if (uniqueFiles.length === 0) return;

    // Validate the proposed new file list
    const proposedFiles = [...files, ...uniqueFiles];
    const validation = validateUploadBatch(proposedFiles);
    setValidationResult(validation);
    
    if (validation.isValid) {
      onFilesChange(proposedFiles);
      toast.success(`Added ${uniqueFiles.length} file${uniqueFiles.length === 1 ? '' : 's'}`);
    } else {
      // Show validation errors but don't update files
      toast.error("Upload validation failed", {
        description: validation.errors[0] // Show first error
      });
    }
  }, [files, onFilesChange]);

  // Re-validate whenever files change
  React.useEffect(() => {
    const validation = validateUploadBatch(files);
    setValidationResult(validation);
  }, [files]);

  const removeFile = useCallback((index: number) => {
    const newFiles = files.filter((_, i) => i !== index);
    onFilesChange(newFiles);
  }, [files, onFilesChange]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    addFiles(acceptedFiles);
  }, [addFiles]);

  const onDragEnter = useCallback(() => {
    setDragActive(true);
  }, []);

  const onDragLeave = useCallback(() => {
    setDragActive(false);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDragEnter,
    onDragLeave,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.ms-powerpoint': ['.ppt'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/vnd.ms-excel': ['.xls'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'text/plain': ['.txt'],
      'text/csv': ['.csv'],
      'text/html': ['.html', '.htm'],
      'text/markdown': ['.md', '.markdown']
    },
    multiple: true,
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all
          ${(isDragActive || dragActive) 
            ? 'border-blue-400 bg-blue-50' 
            : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
          }
        `}
      >
        <input {...getInputProps()} />
        <Upload className={`h-12 w-12 mx-auto mb-4 ${
          (isDragActive || dragActive) ? 'text-blue-500' : 'text-gray-400'
        }`} />
        <div className="space-y-2">
          <h3 className="font-medium text-gray-700">
            {(isDragActive || dragActive) 
              ? 'Drop files here to upload' 
              : 'Drag and drop files here, or click to browse'
            }
          </h3>
          <p className="text-sm text-gray-500">
            Supports PDF, Word, PowerPoint, Excel, and text files up to 50MB each
          </p>
        </div>
      </div>

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
        <Alert variant="default">
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
            <span>
              {formatFileSize(files.reduce((sum, f) => sum + f.size, 0))} of {UPLOAD_LIMITS.MAX_TOTAL_SIZE_MB}MB
            </span>
          </div>
          {!validationResult.isValid && (
            <div className="mt-2 text-xs text-destructive font-medium">
              ⚠ Please fix the issues above before uploading
            </div>
          )}
        </div>
      )}

      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium text-sm text-gray-700">
            Files to Upload ({files.length})
          </h4>
          <div className={cn("space-y-2 max-h-60", ...getScrollbarClasses('y'))}>
            {files.map((file, index) => (
              <FileCard 
                key={`${file.name}-${file.size}-${index}`}
                file={file}
                onRemove={() => removeFile(index)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Browse Button (Alternative) */}
      {files.length === 0 && (
        <div className="text-center">
          <Button 
            variant="outline" 
            onClick={() => (document.querySelector('input[type="file"]') as HTMLInputElement)?.click()}
            className="bg-white"
          >
            <Upload className="h-4 w-4 mr-2" />
            Browse Files
          </Button>
        </div>
      )}
    </div>
  );
}

// File Card Component
interface FileCardProps {
  file: File;
  onRemove: () => void;
}

function FileCard({ file, onRemove }: FileCardProps) {
  const FileIcon = getFileIcon(file);
  const fileSize = formatFileSize(file.size);
  
  return (
    <Card className="transition-all hover:shadow-sm !py-1">
      <CardContent className="!px-3 !py-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 flex-1 min-w-0">
            {/* File Icon */}
            <div className="flex-shrink-0">
              <MinimalistBadge 
                icon={FileIcon} 
                tooltip={`${file.type || 'Unknown type'} file`}
              />
            </div>

            {/* File Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2">
                <p className="font-medium text-sm text-foreground truncate">
                  {file.name}
                </p>
                <span className="inline-flex items-center h-6 px-2 rounded-md bg-muted/50 text-muted-foreground/70 text-xs font-medium">
                  {fileSize}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {file.type || 'Unknown type'}
              </p>
            </div>
          </div>

          {/* Remove Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="flex-shrink-0 ml-2 h-8 w-8 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
} 