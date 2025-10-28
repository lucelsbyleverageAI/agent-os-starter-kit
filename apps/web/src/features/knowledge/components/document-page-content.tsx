"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Eye, Layers, Edit, FileEdit, Trash2, Image as ImageIcon, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { MarkdownText } from "@/components/ui/markdown-text";
import { DocumentContentEditor } from "@/components/ui/document-content-editor";
import { ViewDocumentMetadataDialog } from "./documents-card/view-document-metadata-dialog";
import { ViewDocumentChunksDialog } from "./documents-card/view-document-chunks-dialog";
import { EditDocumentDialog } from "./documents-card/edit-document-dialog";
import { ReplaceImageDialog } from "./documents-card/replace-image-dialog";
import { useAuthContext } from "@/providers/Auth";
import { isImageDocument, getSignedImageUrl } from "@/lib/image-utils";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  downloadMarkdownAsDocx,
  downloadAsMarkdown,
} from "@/lib/markdown-to-docx";

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
  const [showContentEditor, setShowContentEditor] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [savingContent, setSavingContent] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // Image state
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadingImageUrl, setLoadingImageUrl] = useState(false);
  const [showReplaceImageDialog, setShowReplaceImageDialog] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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

  // Fetch signed URL for image documents
  useEffect(() => {
    if (!document || !session?.accessToken) return;

    const fetchImageUrl = async () => {
      // Check if this is an image document
      if (!isImageDocument(document.metadata)) {
        setImageUrl(null);
        return;
      }

      // Check if storage path exists
      const storagePath = document.metadata.storage_path;
      if (!storagePath) {
        console.warn("Image document missing storage_path");
        return;
      }

      // Check if session and accessToken exist
      if (!session?.accessToken) {
        console.warn("No session or access token available");
        return;
      }

      setLoadingImageUrl(true);
      try {
        // Use updated_at timestamp for cache-busting to ensure browser fetches new image after replacement
        const cacheBuster = document.updated_at || Date.now();
        const signedUrl = await getSignedImageUrl(storagePath, session.accessToken, cacheBuster);
        setImageUrl(signedUrl);
      } catch (error) {
        console.error("Failed to fetch signed image URL:", error);
        toast.error("Failed to load image", {
          richColors: true,
          description: "Could not fetch image from storage",
        });
      } finally {
        setLoadingImageUrl(false);
      }
    };

    fetchImageUrl();
  }, [document, session?.accessToken]);

  // Refresh document after edit with polling to wait for background processing
  const handleDocumentUpdated = async (waitForProcessing: boolean = true) => {
    if (!session?.accessToken) return;

    // Store current updated_at to detect when processing completes
    const previousUpdatedAt = document?.updated_at;

    const fetchDocument = async (): Promise<DocumentDetail | null> => {
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

        return await response.json();
      } catch (err) {
        console.error("Error refreshing document:", err);
        return null;
      }
    };

    if (!waitForProcessing) {
      // Just fetch once without polling
      const documentData = await fetchDocument();
      if (documentData) {
        setDocument(documentData);
      }
      return;
    }

    // Poll for updated document (wait for background processing to complete)
    setRefreshing(true);

    const refreshToast = toast.loading("Waiting for processing to complete...", {
      richColors: true,
      description: "Refreshing document with latest changes"
    });

    const maxAttempts = 15; // 15 attempts
    const pollInterval = 1000; // 1 second between attempts
    let attempts = 0;

    const poll = async () => {
      attempts++;
      const documentData = await fetchDocument();

      if (!documentData) {
        // Failed to fetch, stop polling and show error
        if (attempts >= maxAttempts) {
          toast.dismiss(refreshToast);
          toast.error("Failed to refresh document", {
            description: "Please reload the page manually",
            richColors: true,
          });
          setRefreshing(false);
        }
        return;
      }

      // Check if document has been updated (updated_at changed or this is first fetch)
      const hasUpdated = !previousUpdatedAt || documentData.updated_at !== previousUpdatedAt;

      if (hasUpdated || attempts >= maxAttempts) {
        // Processing complete or max attempts reached - update UI
        setDocument(documentData);
        toast.dismiss(refreshToast);

        if (hasUpdated) {
          toast.success("Document refreshed", {
            richColors: true,
            description: "All changes are now visible"
          });
        } else {
          // Max attempts reached without detecting update
          toast.info("Document loaded", {
            richColors: true,
            description: "Some changes may still be processing"
          });
        }

        setRefreshing(false);
      } else {
        // Not updated yet, continue polling
        setTimeout(poll, pollInterval);
      }
    };

    // Start polling after a brief delay to give backend time to start processing
    setTimeout(poll, 500);
  };

  // Save document content changes
  const handleSaveContent = async (newContent: string) => {
    if (!session?.accessToken || !document) return;

    setSavingContent(true);
    const loadingToast = toast.loading("Updating document content", {
      richColors: true,
      description: "Saving changes and re-processing chunks...",
    });

    try {
      const formData = new FormData();
      formData.append("content", newContent);

      const response = await fetch(
        `/api/langconnect/collections/${collectionId}/documents/${documentId}/content`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          body: formData,
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.error || "Failed to update document content");
      }

      const result = await response.json();

      toast.dismiss(loadingToast);
      toast.success("Document content updated successfully", {
        richColors: true,
        description: result.message || "Document is being re-processed in the background",
      });

      setShowContentEditor(false);

      // Refresh document to show updated content
      await handleDocumentUpdated();
    } catch (error) {
      toast.dismiss(loadingToast);
      console.error("Failed to update document content:", error);
      toast.error("Failed to update document content", {
        richColors: true,
        description: error instanceof Error ? error.message : "An error occurred",
      });
    } finally {
      setSavingContent(false);
    }
  };

  // Handle download
  const handleDownload = async (format: "md" | "docx") => {
    if (!document) return;

    try {
      setDownloading(true);

      // Get filename without extension
      const filename = document.title.replace(/\.[^/.]+$/, "");

      // Download in selected format
      if (format === "docx") {
        await downloadMarkdownAsDocx(document.content, filename);
      } else {
        downloadAsMarkdown(document.content, filename);
      }

      toast.success(`Document downloaded successfully`, {
        richColors: true,
        description: `"${document.title}" downloaded as ${format.toUpperCase()}`,
      });
    } catch (error) {
      console.error("Download failed:", error);
      toast.error("Download failed", {
        richColors: true,
        description: error instanceof Error ? error.message : "Failed to download document",
      });
    } finally {
      setDownloading(false);
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
            disabled={!document.metadata || refreshing}
          />
          <MinimalistIconButton
            icon={Layers}
            tooltip="View Chunks"
            onClick={() => setShowChunks(true)}
            disabled={!document.chunks || document.chunks.length === 0 || refreshing}
          />
          <MinimalistIconButton
            icon={Edit}
            tooltip="Edit Metadata"
            onClick={() => setShowEditDialog(true)}
            disabled={refreshing}
          />
          <MinimalistIconButton
            icon={FileEdit}
            tooltip="Edit Content"
            onClick={() => {
              setEditedContent(document.content);
              setShowContentEditor(true);
            }}
            disabled={refreshing}
          />
          {isImageDocument(document.metadata) && (
            <MinimalistIconButton
              icon={ImageIcon}
              tooltip="Replace Image"
              onClick={() => setShowReplaceImageDialog(true)}
              disabled={refreshing}
            />
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                disabled={downloading || refreshing}
              >
                <Download className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => handleDownload("md")}
                disabled={downloading || refreshing}
              >
                Markdown (.md)
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => handleDownload("docx")}
                disabled={downloading || refreshing}
              >
                Word Document (.docx)
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deleting || refreshing}
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
                <AlertDialogCancel className="text-sm" disabled={deleting || refreshing}>
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDeleteDocument}
                  className="bg-destructive hover:bg-destructive/90 text-white text-sm"
                  disabled={deleting || refreshing}
                >
                  {deleting ? "Deleting..." : "Delete Document"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {/* Document Content */}
        {isImageDocument(document.metadata) && imageUrl ? (
          // Two-column layout for image documents
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Image Column */}
            <div
              className={cn(
                "flex items-start justify-center rounded-md border border-border/30 bg-muted/5 p-6 overflow-auto",
                ...getScrollbarClasses("both")
              )}
              style={{ maxHeight: "calc(100vh - 300px)" }}
            >
              {loadingImageUrl ? (
                <div className="flex items-center justify-center h-64">
                  <Skeleton className="w-full h-full" />
                </div>
              ) : (
                <img
                  src={imageUrl}
                  alt={document.title}
                  className="w-full h-auto rounded"
                />
              )}
            </div>

            {/* Content Column */}
            <div
              className={cn(
                "min-h-[600px] overflow-y-auto rounded-md border border-border/30 bg-muted/5 p-6",
                ...getScrollbarClasses("y")
              )}
            >
              <MarkdownText>{document.content}</MarkdownText>
            </div>
          </div>
        ) : (
          // Single column layout for text documents
          <div
            className={cn(
              "min-h-[600px] overflow-y-auto rounded-md border border-border/30 bg-muted/5 p-6",
              ...getScrollbarClasses("y")
            )}
          >
            <MarkdownText>{document.content}</MarkdownText>
          </div>
        )}
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

      {/* Edit Metadata Dialog */}
      <EditDocumentDialog
        documentId={documentId}
        collectionId={collectionId}
        currentTitle={document.title}
        currentDescription={document.description}
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        onSuccess={handleDocumentUpdated}
      />

      {/* Edit Content Dialog */}
      <DocumentContentEditor
        open={showContentEditor}
        onOpenChange={setShowContentEditor}
        value={editedContent}
        onChange={setEditedContent}
        onSave={handleSaveContent}
        title={`Edit: ${document.title}`}
        placeholder="Enter document content here..."
        saving={savingContent}
      />

      {/* Replace Image Dialog */}
      {isImageDocument(document.metadata) && imageUrl && session?.accessToken && (
        <ReplaceImageDialog
          open={showReplaceImageDialog}
          onOpenChange={setShowReplaceImageDialog}
          documentId={documentId}
          collectionId={collectionId}
          currentImageUrl={imageUrl}
          currentTitle={document.title}
          accessToken={session.accessToken}
          onSuccess={handleDocumentUpdated}
        />
      )}
    </>
  );
}
