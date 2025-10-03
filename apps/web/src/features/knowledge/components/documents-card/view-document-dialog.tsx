"use client";

import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Eye, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { MarkdownText } from "@/components/ui/markdown-text";
import { ViewDocumentMetadataDialog } from "./view-document-metadata-dialog";
import { ViewDocumentChunksDialog } from "./view-document-chunks-dialog";
import { useAuthContext } from "@/providers/Auth";

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
  chunks?: Array<{
    id: string;
    content_preview: string;
    content: string;
    content_length: number;
    metadata: Record<string, any>;
    embedding?: any;
  }>;
}

interface ViewDocumentDialogProps {
  documentId: string | null;
  collectionId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ViewDocumentDialog({
  documentId,
  collectionId,
  open,
  onOpenChange,
}: ViewDocumentDialogProps) {
  const { session } = useAuthContext();
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMetadata, setShowMetadata] = useState(false);
  const [showChunks, setShowChunks] = useState(false);

  // Fetch document details when dialog opens
  useEffect(() => {
    if (!open || !documentId || !collectionId) {
      setDocument(null);
      setError(null);
      return;
    }

    const fetchDocument = async () => {
      if (!session?.accessToken) {
        setError("No authentication session found");
        toast.error("Authentication required", {
          description: "Please log in to view documents",
          richColors: true,
        });
        return;
      }

      setLoading(true);
      setError(null);
      
      try {
        const response = await fetch(`/api/langconnect/collections/${collectionId}/documents/${documentId}?include_chunks=true`, {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });
        
        if (!response.ok) {
          throw new Error(`Failed to fetch document: ${response.statusText}`);
        }
        
        const documentData: DocumentDetail = await response.json();
        setDocument(documentData);
      } catch (err) {
        console.error("Error fetching document:", err);
        setError(err instanceof Error ? err.message : "Failed to fetch document");
        toast.error("Failed to load document", {
          description: err instanceof Error ? err.message : "Unknown error occurred",
          richColors: true,
        });
      } finally {
        setLoading(false);
      }
    };

    fetchDocument();
  }, [open, documentId, collectionId]);

  // Reset state when dialog closes
  const handleClose = () => {
    setShowMetadata(false);
    setShowChunks(false);
    onOpenChange(false);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className={cn("!max-w-5xl !w-[80vw] max-h-[90vh] flex flex-col gap-0", ...getScrollbarClasses('y'))}>
          <DialogHeader className="flex-shrink-0 pb-4">
            <DialogTitle className="text-xl font-semibold">
              {loading ? "Loading Document..." : error ? "Error Loading Document" : document ? document.title : "Document"}
            </DialogTitle>
            {loading ? (
              <Skeleton className="h-4 w-48 mt-1" />
            ) : error ? (
              <p className="text-sm text-muted-foreground mt-1">{error}</p>
            ) : document && document.description ? (
              <p className="text-sm text-muted-foreground mt-1">{document.description}</p>
            ) : null}
          </DialogHeader>

          <div className="flex-1 min-h-0 flex flex-col gap-3">
            {loading ? (
              <div className="flex flex-col gap-3">
                <div className="flex justify-end gap-2">
                  <Skeleton className="h-8 w-8" />
                  <Skeleton className="h-8 w-8" />
                </div>
                <Skeleton className="h-[400px] w-full" />
              </div>
            ) : error ? (
              <Card>
                <CardContent className="pt-6">
                  <p className="text-center text-muted-foreground">
                    Unable to load document content.
                  </p>
                </CardContent>
              </Card>
            ) : document ? (
              <>
                {/* Action Buttons */}
                <div className="flex justify-end gap-2">
                  <MinimalistIconButton
                    icon={Eye}
                    tooltip="View Metadata"
                    onClick={() => setShowMetadata(true)}
                    disabled={!document.metadata}
                  />
                  <MinimalistIconButton
                    icon={Layers}
                    tooltip="View Chunks"
                    onClick={() => setShowChunks(true)}
                    disabled={!document.chunks || document.chunks.length === 0}
                  />
                </div>

                {/* Document Content - Minimal styling */}
                <div className={cn(
                  "flex-1 min-h-0 overflow-y-auto rounded-md border border-border/30 bg-muted/5 p-6",
                  ...getScrollbarClasses('y')
                )}>
                  <MarkdownText>{document.content}</MarkdownText>
                </div>
              </>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>

      {/* Metadata Dialog */}
      {document && (
        <ViewDocumentMetadataDialog
          open={showMetadata}
          onOpenChange={setShowMetadata}
          document={document}
        />
      )}

      {/* Chunks Dialog */}
      {document && document.chunks && (
        <ViewDocumentChunksDialog
          open={showChunks}
          onOpenChange={setShowChunks}
          chunks={document.chunks || []}
          documentTitle={document.title}
        />
      )}
    </>
  );
} 