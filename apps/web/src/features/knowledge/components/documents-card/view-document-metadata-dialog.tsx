"use client";

import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { format } from "date-fns";

interface DocumentDetail {
  id: string;
  collection_id: string;
  title: string;
  description: string;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  chunk_count?: number;
}

interface ViewDocumentMetadataDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  document: DocumentDetail;
}

const formatMetadataValue = (key: string, value: any): string => {
  if (value === null || value === undefined) {
    return "Not available";
  }
  
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  
  if (typeof value === "number") {
    // Format file sizes
    if (key.toLowerCase().includes("size") && value > 1024) {
      if (value > 1024 * 1024) {
        return `${(value / (1024 * 1024)).toFixed(2)} MB`;
      }
      return `${(value / 1024).toFixed(2)} KB`;
    }
    return value.toLocaleString();
  }
  
  if (typeof value === "string") {
    // Format dates
    if (key.toLowerCase().includes("date") || key.toLowerCase().includes("time") || key.toLowerCase().includes("at")) {
      try {
        const date = new Date(value);
        if (!isNaN(date.getTime())) {
          return format(date, "PPpp");
        }
      } catch {
        // Fall through to default string handling
      }
    }
    return value;
  }
  
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  
  return String(value);
};

const getMetadataKeyLabel = (key: string): string => {
  // Convert snake_case and camelCase to readable labels
  return key
    .replace(/[_-]/g, " ")
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (str) => str.toUpperCase())
    .trim();
};

export function ViewDocumentMetadataDialog({
  open,
  onOpenChange,
  document,
}: ViewDocumentMetadataDialogProps) {
  // Group metadata into categories for better organization
  const coreFields = [
    { key: "title", value: document.title },
    { key: "description", value: document.description },
    { key: "id", value: document.id },
    { key: "collection_id", value: document.collection_id },
    { key: "created_at", value: document.created_at },
    { key: "updated_at", value: document.updated_at },
    { key: "chunk_count", value: document.chunk_count },
  ];

  const metadataFields = Object.entries(document.metadata || {})
    .filter(([key]) => !["title", "description"].includes(key)) // Avoid duplicates
    .map(([key, value]) => ({ key, value }));

  const allFields = [...coreFields, ...metadataFields].filter(
    ({ value }) => value !== undefined && value !== null && value !== ""
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-w-2xl max-h-[80vh] flex flex-col gap-0", ...getScrollbarClasses('y'))}>
        <DialogHeader className="pb-4">
          <DialogTitle>Document Metadata</DialogTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Detailed information about "{document.title}"
          </p>
        </DialogHeader>

        <div className={cn("flex-1 min-h-0 overflow-y-auto", ...getScrollbarClasses('y'))}>
          {allFields.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  No metadata available for this document.
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Document Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {allFields.map(({ key, value }) => {
                  const formattedValue = formatMetadataValue(key, value);
                  const isLongValue = formattedValue.length > 100;
                  
                  return (
                    <div key={key} className="grid grid-cols-1 gap-2">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <dt className="font-medium text-sm text-foreground">
                            {getMetadataKeyLabel(key)}
                          </dt>
                          <dd className={cn(
                            "text-sm text-muted-foreground mt-1",
                            isLongValue && "font-mono text-xs"
                          )}>
                            {isLongValue ? (
                              <pre className="whitespace-pre-wrap break-words">
                                {formattedValue}
                              </pre>
                            ) : (
                              formattedValue
                            )}
                          </dd>
                        </div>
                        {typeof value === "boolean" && (
                          <Badge variant={value ? "default" : "secondary"} className="ml-2">
                            {value ? "Yes" : "No"}
                          </Badge>
                        )}
                      </div>
                      {key !== allFields[allFields.length - 1].key && (
                        <hr className="border-border/50" />
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
} 