"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  FileText, 
  AlertCircle, 
  RefreshCw,
  Calendar,
  Hash
} from "lucide-react";
import { ProcessingJob } from "@/hooks/use-job-tracking";
import { formatDistanceToNow } from "date-fns";

interface DuplicateDetectionDialogProps {
  job: ProcessingJob | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DuplicateDetectionDialog({
  job,
  open,
  onOpenChange,
}: DuplicateDetectionDialogProps) {
  if (!job || !job.duplicate_summary) {
    return null;
  }

  const { duplicate_summary, files_skipped, files_overwritten } = job;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-orange-500" />
            Duplicate Detection Results
          </DialogTitle>
          <DialogDescription>
            Processing results for "{job.title}" - duplicate files were detected and handled automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Summary Section */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-muted/50 rounded-lg">
              <div className="text-2xl font-bold text-foreground">
                {duplicate_summary.total_files_checked}
              </div>
              <div className="text-sm text-muted-foreground">
                Files Checked
              </div>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <div className="text-2xl font-bold text-green-700">
                {duplicate_summary.total_files_to_process}
              </div>
              <div className="text-sm text-green-600">
                Processed
              </div>
            </div>
            <div className="text-center p-3 bg-orange-50 rounded-lg">
              <div className="text-2xl font-bold text-orange-700">
                {duplicate_summary.total_files_skipped}
              </div>
              <div className="text-sm text-orange-600">
                Skipped
              </div>
            </div>
            <div className="text-center p-3 bg-blue-50 rounded-lg">
              <div className="text-2xl font-bold text-blue-700">
                {duplicate_summary.files_overwritten}
              </div>
              <div className="text-sm text-blue-600">
                Overwritten
              </div>
            </div>
          </div>

          {/* Skipped Files Section */}
          {files_skipped && files_skipped.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-orange-500" />
                Skipped Files ({files_skipped.length})
              </h3>
              <ScrollArea className="h-64 border rounded-lg">
                <div className="p-4 space-y-3">
                  {files_skipped.map((file, index) => (
                    <div key={index} className="border-l-4 border-orange-200 pl-4 py-2">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium text-sm">{file.filename}</span>
                            <Badge variant="outline" className="text-xs">
                              {file.action}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mb-2">
                            {file.reason}
                          </p>
                          {file.existing_document && (
                            <div className="bg-muted/30 p-2 rounded text-xs space-y-1">
                              <div className="font-medium">Existing Document:</div>
                              <div>Title: {file.existing_document.title}</div>
                              <div>Original: {file.existing_document.original_filename}</div>
                              <div className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Created {formatDistanceToNow(new Date(file.existing_document.created_at), { addSuffix: true })}
                              </div>
                            </div>
                          )}
                          {file.content_hash && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                              <Hash className="h-3 w-3" />
                              <span className="font-mono">{file.content_hash.substring(0, 16)}...</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}

          {/* Overwritten Files Section */}
          {files_overwritten && files_overwritten.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <RefreshCw className="h-5 w-5 text-blue-500" />
                Overwritten Files ({files_overwritten.length})
              </h3>
              <ScrollArea className="h-64 border rounded-lg">
                <div className="p-4 space-y-3">
                  {files_overwritten.map((file, index) => (
                    <div key={index} className="border-l-4 border-blue-200 pl-4 py-2">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium text-sm">{file.filename}</span>
                            <Badge variant="outline" className="text-xs">
                              {file.action}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mb-2">
                            {file.reason}
                          </p>
                          {file.previous_document && (
                            <div className="bg-muted/30 p-2 rounded text-xs space-y-1">
                              <div className="font-medium">Previous Document:</div>
                              <div>Title: {file.previous_document.title}</div>
                              <div>Original: {file.previous_document.original_filename}</div>
                              <div className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Created {formatDistanceToNow(new Date(file.previous_document.created_at), { addSuffix: true })}
                              </div>
                            </div>
                          )}
                          {file.content_hash && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                              <Hash className="h-3 w-3" />
                              <span className="font-mono">{file.content_hash.substring(0, 16)}...</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
} 