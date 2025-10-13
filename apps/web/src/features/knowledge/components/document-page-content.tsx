"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Eye, Layers, Edit, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { MarkdownText } from "@/components/ui/markdown-text";
import { ViewDocumentMetadataDialog } from "./documents-card/view-document-metadata-dialog";
import { ViewDocumentChunksDialog } from "./documents-card/view-document-chunks-dialog";
import { EditDocumentDialog } from "./documents-card/edit-document-dialog";
import { useAuthContext } from "@/providers/Auth";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useKnowledgeContext } from "../providers/Knowledge";
import { useRouter } from "next/navigation";

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

interface DocumentPageContentProps {
  documentId: string;
  collectionId: string;
  onDocumentDeleted?: () => void;
}

/**
 * Document page content showing document details, content, and actions.
 * Extracted from ViewDocumentDialog to be used in dedicated document pages.
 */
export function DocumentPageContent({
  documentId,
  collectionId,
  onDocumentDeleted,
}: DocumentPageContentProps) {
  const { session } = useAuthContext();
  const { deleteDocument } = useKnowledgeContext();
  const router = useRouter();
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMetadata, setShowMetadata] = useState(false);
  const [showChunks, setShowChunks] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Fetch document details
  useEffect(() => {
    if (!documentId || !collectionId) {
      setError("Missing document or collection ID");
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
        const response = await fetch(
          `/api/langconnect/collections/${collectionId}/documents/${documentId}?include_chunks=true`,
          {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch document: ${response.statusText}`);
        }

        const documentData: DocumentDetail = await response.json();
        setDocument(documentData);
      } catch (err) {
        console.error("Error fetching document:", err);
        setError(err instanceof Error ? err.message : "Failed to fetch document");
        toast.error("Failed to load document", {
          description:
            err instanceof Error ? err.message : "Unknown error occurred",
          richColors: true,
        });
      } finally {
        setLoading(false);
      }
    };

    fetchDocument();
  }, [documentId, collectionId, session?.accessToken]);

  // Refresh document after edit
  const handleDocumentUpdated = async () => {
    if (!session?.accessToken) return;

    try {
      const response = await fetch(
        `/api/langconnect/collections/${collectionId}/documents/${documentId}?include_chunks=true`,
        {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to refresh document: ${response.statusText}`);
      }

      const documentData: DocumentDetail = await response.json();
      setDocument(documentData);
    } catch (err) {
      console.error("Error refreshing document:", err);
      toast.error("Failed to refresh document", {
        description: "Please reload the page",
        richColors: true,
      });
    }
  };

  // Handle document deletion
  const handleDeleteDocument = async () => {
    if (!document) return;

    const loadingToast = toast.loading("Deleting document", {
      richColors: true,
      description: `Removing "${document.title}" from collection...`,
    });

    setDeleting(true);

    try {
      await deleteDocument(documentId, document.title, collectionId);

      toast.dismiss(loadingToast);
      toast.success("Document deleted successfully", {
        richColors: true,
        description: `"${document.title}" has been removed from the collection.`,
      });

      // Navigate back to collection page
      router.push(`/knowledge/${collectionId}`);

      if (onDocumentDeleted) {
        onDocumentDeleted();
      }
    } catch (error) {
      toast.dismiss(loadingToast);
      console.error("❌ Delete document error:", error);

      let errorMessage = "Failed to delete document";
      let errorDescription = "Unknown error occurred";

      if (error instanceof Error) {
        errorDescription = error.message;

        if (
          error.message.includes("permission") ||
          error.message.includes("403")
        ) {
          errorMessage = "Permission denied";
          errorDescription = "You don't have permission to delete this document.";
        } else if (
          error.message.includes("404") ||
          error.message.includes("not found")
        ) {
          errorMessage = "Document not found";
          errorDescription = "The document may have already been deleted.";
        }
      }

      toast.error(errorMessage, {
        richColors: true,
        description: errorDescription,
      });
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex justify-end gap-2">
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
        </div>
        <Skeleton className="h-[600px] w-full" />
      </div>
    );
  }

  if (error || !document) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-muted-foreground">
            {error || "Unable to load document content."}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-4">
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
          <MinimalistIconButton
            icon={Edit}
            tooltip="Edit Document"
            onClick={() => setShowEditDialog(true)}
          />
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deleting}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="text-lg font-medium">
                  Delete Document
                </AlertDialogTitle>
                <AlertDialogDescription className="text-sm text-muted-foreground">
                  Are you sure you want to delete
                  <span className="font-medium text-foreground">
                    {" "}
                    "{document.title}"
                  </span>
                  ? This action cannot be undone and will permanently remove the
                  document from your collection.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="text-sm" disabled={deleting}>
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDeleteDocument}
                  className="bg-destructive hover:bg-destructive/90 text-white text-sm"
                  disabled={deleting}
                >
                  {deleting ? "Deleting..." : "Delete Document"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {/* Document Content */}
        <div
          className={cn(
            "min-h-[600px] overflow-y-auto rounded-md border border-border/30 bg-muted/5 p-6",
            ...getScrollbarClasses("y")
          )}
        >
          <MarkdownText>{document.content}</MarkdownText>
        </div>
      </div>

      {/* Metadata Dialog */}
      <ViewDocumentMetadataDialog
        open={showMetadata}
        onOpenChange={setShowMetadata}
        document={document}
      />

      {/* Chunks Dialog */}
      {document.chunks && (
        <ViewDocumentChunksDialog
          open={showChunks}
          onOpenChange={setShowChunks}
          chunks={document.chunks || []}
          documentTitle={document.title}
        />
      )}

      {/* Edit Dialog */}
      <EditDocumentDialog
        documentId={documentId}
        collectionId={collectionId}
        currentTitle={document.title}
        currentDescription={document.description}
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        onSuccess={handleDocumentUpdated}
      />
    </>
  );
}
