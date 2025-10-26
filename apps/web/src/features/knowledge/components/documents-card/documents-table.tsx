"use client";

import type React from "react";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import {
  Trash2,
  MoreVertical,
  Loader2,
  X,
  Search,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Files,
  Edit,
  Download
} from "lucide-react";
import { Document } from "@langchain/core/documents";
import { useKnowledgeContext } from "../../providers/Knowledge";
import { format } from "date-fns";
import { Collection } from "@/types/collection";
import { toast } from "sonner";
import { EditDocumentDialog } from "./edit-document-dialog";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { useRouter } from "next/navigation";
import {
  downloadMarkdownAsDocx,
  downloadAsMarkdown,
} from "@/lib/markdown-to-docx";
import {
  DropdownMenu as DownloadFormatMenu,
  DropdownMenuContent as DownloadFormatContent,
  DropdownMenuItem as DownloadFormatItem,
  DropdownMenuTrigger as DownloadFormatTrigger,
} from "@/components/ui/dropdown-menu";

// Truncate title helper
const truncateTitle = (title: string, maxLength: number = 50): { truncated: string; isTruncated: boolean } => {
  if (title.length <= maxLength) {
    return { truncated: title, isTruncated: false };
  }
  return { truncated: `${title.substring(0, maxLength)}...`, isTruncated: true };
};

// URL detection helper
const isValidUrl = (string: string): boolean => {
  try {
    new URL(string);
    return true;
  } catch (_) {
    return false;
  }
};

// Sort configuration
type SortField = 'name' | 'date';
type SortDirection = 'asc' | 'desc';

interface SortConfig {
  field: SortField;
  direction: SortDirection;
}

// Fuzzy search helper
const fuzzyMatch = (searchTerm: string, text: string): boolean => {
  if (!searchTerm) return true;
  
  const search = searchTerm.toLowerCase();
  const target = text.toLowerCase();
  
  // Simple fuzzy matching: check if all characters of search term appear in order
  let searchIndex = 0;
  for (let i = 0; i < target.length && searchIndex < search.length; i++) {
    if (target[i] === search[searchIndex]) {
      searchIndex++;
    }
  }
  
  return searchIndex === search.length || target.includes(search);
};

interface DocumentsTableProps {
  documents: Document[];
  selectedCollection: Collection;
  actionsDisabled: boolean;
  onDocumentDeleted?: () => void | Promise<void>;
  onDocumentsChanged?: () => void | Promise<void>; // Generic callback for any document changes
  onLoadMore?: () => Promise<void>;
  hasMore?: boolean;
  loading?: boolean;
  totalDocumentCount?: number; // Override for total count when using infinite scroll
}

export function DocumentsTable({
  documents,
  selectedCollection,
  actionsDisabled,
  onDocumentDeleted,
  onDocumentsChanged,
  onLoadMore,
  hasMore = false,
  loading = false,
  totalDocumentCount,
}: DocumentsTableProps) {
  const router = useRouter();
  const { deleteDocument } = useKnowledgeContext();
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
  const [editDocumentId, setEditDocumentId] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  
  // Multi-select state
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [showBatchDeleteDialog, setShowBatchDeleteDialog] = useState(false);
  
  // Search and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState<SortConfig>({ field: 'date', direction: 'desc' });

  // Download state
  const [downloadingDocumentId, setDownloadingDocumentId] = useState<string | null>(null);
  const [downloadFormatMenu, setDownloadFormatMenu] = useState<string | null>(null);

  // Refs for infinite scroll
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreTriggerRef = useRef<HTMLDivElement>(null);

  // Filtered and sorted documents
  const processedDocuments = useMemo(() => {
    let filtered = documents;
    
    // Apply search filter
    if (searchTerm.trim()) {
      filtered = documents.filter(doc => 
        fuzzyMatch(searchTerm, doc.metadata.name)
      );
    }
    
    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let comparison = 0;
      
      if (sortConfig.field === 'name') {
        comparison = a.metadata.name.localeCompare(b.metadata.name);
      } else if (sortConfig.field === 'date') {
        const dateA = new Date(a.metadata.created_at).getTime();
        const dateB = new Date(b.metadata.created_at).getTime();
        comparison = dateA - dateB;
      }
      
      return sortConfig.direction === 'asc' ? comparison : -comparison;
    });
    
    return sorted;
  }, [documents, searchTerm, sortConfig]);

  // Handle sorting
  const handleSort = useCallback((field: SortField) => {
    setSortConfig(prev => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  }, []);

  // Get sort icon for column header
  const getSortIcon = useCallback((field: SortField) => {
    if (sortConfig.field !== field) {
      return <ChevronsUpDown className="h-3 w-3 ml-1 text-muted-foreground/50" />;
    }
    
    return sortConfig.direction === 'asc' 
      ? <ChevronUp className="h-3 w-3 ml-1 text-foreground" />
      : <ChevronDown className="h-3 w-3 ml-1 text-foreground" />;
  }, [sortConfig]);

  // Multi-select handlers
  const isAllVisibleSelected = processedDocuments.length > 0 && processedDocuments.every(doc => selectedDocuments.has(doc.metadata.file_id));
  const isIndeterminate = selectedDocuments.size > 0 && !isAllVisibleSelected;

  const handleSelectAll = useCallback((checked: boolean) => {
    if (checked) {
      const newSelected = new Set(selectedDocuments);
      processedDocuments.forEach(doc => newSelected.add(doc.metadata.file_id));
      setSelectedDocuments(newSelected);
    } else {
      const newSelected = new Set(selectedDocuments);
      processedDocuments.forEach(doc => newSelected.delete(doc.metadata.file_id));
      setSelectedDocuments(newSelected);
    }
  }, [processedDocuments, selectedDocuments]);

  const handleSelectDocument = useCallback((documentId: string, checked: boolean) => {
    const newSelected = new Set(selectedDocuments);
    if (checked) {
      newSelected.add(documentId);
    } else {
      newSelected.delete(documentId);
    }
    setSelectedDocuments(newSelected);
  }, [selectedDocuments]);

  const clearSelection = useCallback(() => {
    setSelectedDocuments(new Set());
  }, []);

  // Get selected document details for batch operations
  const selectedDocumentDetails = processedDocuments.filter(doc => selectedDocuments.has(doc.metadata.file_id));

  // Handle batch delete
  const handleBatchDelete = useCallback(async () => {
    if (selectedDocuments.size === 0) return;

    // Check if user has permission to delete
    const canDelete = selectedCollection.permission_level === 'owner' || selectedCollection.permission_level === 'editor';
    if (!canDelete) {
      toast.error("Insufficient permissions", {
        richColors: true,
        description: "You don't have permission to delete documents from this collection."
      });
      return;
    }

    setBatchDeleting(true);
    setShowBatchDeleteDialog(false);

    const documentsToDelete = Array.from(selectedDocuments);
    const totalCount = documentsToDelete.length;
    let successCount = 0;
    let failureCount = 0;

    const loadingToast = toast.loading(`Deleting ${totalCount} documents...`, {
      richColors: true,
    });

    try {
      // Delete documents one by one (could be optimized with batch API in future)
      for (const documentId of documentsToDelete) {
        try {
          const doc = documents.find(d => d.metadata.file_id === documentId);
          const docName = doc?.metadata.name || "Unknown document";
          await deleteDocument(documentId, docName, selectedCollection.uuid);
          successCount++;
        } catch (_error) {
          console.error(`Failed to delete document ${documentId}:`, _error);
          failureCount++;
        }
      }

      toast.dismiss(loadingToast);

      if (failureCount === 0) {
        toast.success(`Successfully deleted ${successCount} documents`, {
          richColors: true,
        });
      } else {
        toast.warning(`Deleted ${successCount} documents, ${failureCount} failed`, {
          richColors: true,
          description: "Some documents could not be deleted. Please try again."
        });
      }

      // Clear selection and refresh
      clearSelection();
      if (onDocumentDeleted) {
        await onDocumentDeleted();
      }

    } catch (_error) {
      toast.dismiss(loadingToast);
      toast.error("Batch delete failed", {
        richColors: true,
        description: "An unexpected error occurred during batch deletion."
      });
    } finally {
      setBatchDeleting(false);
    }
  }, [selectedDocuments, selectedCollection.permission_level, documents, deleteDocument, clearSelection, onDocumentDeleted]);

  // Handle document deletion with proper loading states and error handling
  const handleDeleteDocument = async (documentId: string, documentName: string) => {
    // Double-check that the document still exists in our local state
    const documentExists = documents.some(doc => doc.metadata.file_id === documentId);
    if (!documentExists) {
      toast.error("Document not found", {
        richColors: true,
        description: "The document may have already been deleted."
      });
      return;
    }

    // Check if user has permission to delete (based on collection permissions)
    const canDelete = selectedCollection.permission_level === 'owner' || selectedCollection.permission_level === 'editor';
    if (!canDelete) {
      toast.error("Insufficient permissions", {
        richColors: true,
        description: "You don't have permission to delete documents from this collection."
      });
      return;
    }

    const loadingToast = toast.loading("Deleting document", {
      richColors: true,
      description: `Removing "${documentName}" from collection...`
    });
    
    setDeletingDocumentId(documentId);
    
    try {
      await deleteDocument(documentId, documentName, selectedCollection.uuid);
      
      toast.dismiss(loadingToast);
      toast.success("Document deleted successfully", { 
        richColors: true,
        description: `"${documentName}" has been removed from the collection.`
      });
      
      // Remove from selection if it was selected
      if (selectedDocuments.has(documentId)) {
        const newSelected = new Set(selectedDocuments);
        newSelected.delete(documentId);
        setSelectedDocuments(newSelected);
      }
      
      // Call the callback to refresh the parent's document list
      if (onDocumentDeleted) {
        await onDocumentDeleted();
      }
      
    } catch (error) {
      toast.dismiss(loadingToast);
      console.error("❌ Delete document error:", error);
      
      // Provide more specific error messages based on error type
      let errorMessage = "Failed to delete document";
      let errorDescription = "Unknown error occurred";
      
      if (error instanceof Error) {
        errorDescription = error.message;
        
        // Check for specific error types
        if (error.message.includes('permission') || error.message.includes('403')) {
          errorMessage = "Permission denied";
          errorDescription = "You don't have permission to delete this document.";
        } else if (error.message.includes('404') || error.message.includes('not found')) {
          errorMessage = "Document not found";
          errorDescription = "The document may have already been deleted.";
        } else if (error.message.includes('500')) {
          errorMessage = "Server error";
          errorDescription = "Please try again later or contact support.";
        }
      }
      
      toast.error(errorMessage, { 
        richColors: true,
        description: errorDescription
      });
    } finally {
      setDeletingDocumentId(null);
    }
  };

  // Handle document download
  const handleDownloadDocument = useCallback(async (documentId: string, documentName: string, format: "md" | "docx") => {
    try {
      setDownloadingDocumentId(documentId);
      setDownloadFormatMenu(null);

      // Fetch document content
      const response = await fetch(
        `/api/langconnect/collections/${selectedCollection.uuid}/documents/${documentId}/content`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch document: ${response.statusText}`);
      }

      const data = await response.json();
      const content = data.content || "";

      // Get filename without extension
      const filename = documentName.replace(/\.[^/.]+$/, "");

      // Download in selected format
      if (format === "docx") {
        await downloadMarkdownAsDocx(content, filename);
      } else {
        downloadAsMarkdown(content, filename);
      }

      toast.success(`Document downloaded successfully`, {
        richColors: true,
        description: `"${documentName}" downloaded as ${format.toUpperCase()}`,
      });
    } catch (error) {
      console.error("Download failed:", error);
      toast.error("Download failed", {
        richColors: true,
        description: error instanceof Error ? error.message : "Failed to download document",
      });
    } finally {
      setDownloadingDocumentId(null);
    }
  }, [selectedCollection.uuid]);

  // Handle infinite scroll
  const handleLoadMore = useCallback(async () => {
    if (!onLoadMore || loadingMore || !hasMore) return;
    
    setLoadingMore(true);
    try {
      await onLoadMore();
    } catch (error) {
      console.error('Failed to load more documents:', error);
      toast.error("Failed to load more documents", {
        richColors: true,
        description: "Please try again"
      });
    } finally {
      setLoadingMore(false);
    }
  }, [onLoadMore, loadingMore, hasMore]);

  // Intersection Observer for infinite scroll
  useEffect(() => {
    const trigger = loadMoreTriggerRef.current;
    if (!trigger || !hasMore || loadingMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry.isIntersecting) {
          handleLoadMore();
        }
      },
      {
        threshold: 0.1,
        rootMargin: '100px',
      }
    );

    observer.observe(trigger);

    return () => {
      observer.unobserve(trigger);
    };
  }, [handleLoadMore, hasMore, loadingMore]);

  // Clear selection when documents change (e.g., after refresh)
  useEffect(() => {
    setSelectedDocuments(prev => {
      const currentDocumentIds = new Set(documents.map(doc => doc.metadata.file_id));
      const filteredSelection = new Set(Array.from(prev).filter(id => currentDocumentIds.has(id)));
      return filteredSelection;
    });
  }, [documents]);

  // Clear search when no documents match
  const clearSearch = useCallback(() => {
    setSearchTerm('');
  }, []);

  return (
    <div className="space-y-4 p-1">
      {/* Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9 pr-9 focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          {searchTerm && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearSearch}
              className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0 hover:bg-muted"
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
        
        {/* Document Count Badge */}
        <div className="flex items-center">
          <MinimalistBadgeWithText
            icon={Files}
            text={searchTerm ? 
              `${processedDocuments.length} of ${totalDocumentCount ?? documents.length}` : 
              `${totalDocumentCount ?? documents.length}`
            }
            tooltip={searchTerm ? 
              `Showing ${processedDocuments.length} documents matching "${searchTerm}" out of ${totalDocumentCount ?? documents.length} total` :
              `${totalDocumentCount ?? documents.length} documents in this collection`
            }
          />
        </div>
      </div>

      <div className="rounded-xl border border-border overflow-hidden">
        {/* Bulk Actions Bar */}
        {selectedDocuments.size > 0 && (
          <div className="bg-primary/10 border-b border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">
                  {selectedDocuments.size} document{selectedDocuments.size === 1 ? '' : 's'} selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearSelection}
                  className="h-7 px-2 text-xs"
                >
                  <X className="h-3 w-3 mr-1" />
                  Clear
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setShowBatchDeleteDialog(true)}
                  disabled={batchDeleting || actionsDisabled}
                  className="h-7 px-3 text-xs"
                >
                  <Trash2 className="h-3 w-3 mr-1" />
                  {batchDeleting ? "Deleting..." : "Delete Selected"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Frozen Header */}
        <div className="bg-muted/30 border-b border-border">
          <div className="grid grid-cols-12 gap-4 px-4 py-3">
            <div className="col-span-1 flex items-center">
              <Checkbox
                checked={isAllVisibleSelected}
                onCheckedChange={handleSelectAll}
                disabled={processedDocuments.length === 0 || loading}
                className="data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground"
                {...(isIndeterminate && { 'data-state': 'indeterminate' })}
              />
            </div>
            <div className="col-span-3 flex items-center">
              <button
                onClick={() => handleSort('name')}
                className="flex items-center text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Title
                {getSortIcon('name')}
              </button>
            </div>
            <div className="col-span-5 text-xs font-medium text-muted-foreground">
              Description
            </div>
            <div className="col-span-1 flex items-center">
              <button
                onClick={() => handleSort('date')}
                className="flex items-center text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Date
                {getSortIcon('date')}
              </button>
            </div>
            <div className="col-span-2 text-xs font-medium text-muted-foreground text-right">
              Actions
            </div>
          </div>
        </div>

        {/* Scrollable Content */}
        <div 
          ref={tableContainerRef}
          className={cn(
            "max-h-[60vh] overflow-y-auto",
            ...getScrollbarClasses('y')
          )}
        >
          {processedDocuments.length === 0 && !loading ? (
            <div className="text-sm text-muted-foreground text-center py-8 px-4">
              {searchTerm ? (
                <div className="space-y-2">
                  <div>No documents found matching "{searchTerm}"</div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearSearch}
                    className="text-xs"
                  >
                    Clear search
                  </Button>
                </div>
              ) : (
                "No documents found in this collection."
              )}
            </div>
          ) : (
            <>
              {processedDocuments.map((doc, index) => {
                const { truncated: displayName, isTruncated } = truncateTitle(doc.metadata.name);
                const isLastRow = index === processedDocuments.length - 1;
                const isSelected = selectedDocuments.has(doc.metadata.file_id);

                // Handler for row click navigation
                const handleRowClick = () => {
                  router.push(`/knowledge/${selectedCollection.uuid}/document/${doc.metadata.file_id}`);
                };

                return (
                  <div
                    key={doc.id}
                    className={cn(
                      "grid grid-cols-12 gap-4 px-4 py-3 hover:bg-accent/50 transition-colors",
                      !isLastRow && "border-b border-border/30",
                      deletingDocumentId === doc.metadata.file_id && "opacity-50 pointer-events-none",
                      isSelected && "bg-primary/5"
                    )}
                  >
                    {/* Checkbox */}
                    <div className="col-span-1 flex items-center">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={(checked: boolean) => handleSelectDocument(doc.metadata.file_id, checked)}
                        disabled={deletingDocumentId === doc.metadata.file_id || batchDeleting}
                      />
                    </div>

                    {/* Document Name */}
                    <div className="col-span-3 flex items-center cursor-pointer" onClick={handleRowClick}>
                      {(() => {
                        // Only treat as URL if it's from URL upload (has source_type of 'url')
                        const isUrl = doc.metadata.source_type === 'url' && isValidUrl(doc.metadata.name);
                        const commonClasses = "text-sm font-normal truncate";
                        const linkClasses = isUrl
                          ? "text-blue-600 hover:text-blue-800 hover:underline"
                          : "text-foreground";

                        const handleClick = isUrl ? (e: React.MouseEvent) => {
                          e.stopPropagation(); // Prevent row click when opening URL
                          window.open(doc.metadata.name, '_blank', 'noopener,noreferrer');
                        } : undefined;
                        
                        if (isTruncated) {
                          return (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    className={cn(commonClasses, linkClasses)}
                                    onClick={handleClick}
                                  >
                                    {displayName}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="max-w-xs break-words text-sm">
                                    {isUrl ? (
                                      <>
                                        <span className="font-medium">Click to open URL</span>
                                        <br />
                                        {doc.metadata.name}
                                      </>
                                    ) : (
                                      doc.metadata.name
                                    )}
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          );
                        } else {
                          return (
                            <span
                              className={cn(commonClasses, linkClasses)}
                              onClick={handleClick}
                              title={isUrl ? "Click to open URL in new tab" : undefined}
                            >
                              {displayName}
                            </span>
                          );
                        }
                      })()}
                    </div>

                    {/* Description */}
                    <div className="col-span-5 flex items-center cursor-pointer" onClick={handleRowClick}>
                      {doc.metadata.description ? (
                        <TooltipProvider>
                          <Tooltip delayDuration={300}>
                            <TooltipTrigger asChild>
                              <p className="text-sm text-muted-foreground line-clamp-2">
                                {doc.metadata.description}
                              </p>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-md">
                              <p className="text-sm whitespace-pre-wrap">
                                {doc.metadata.description}
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ) : (
                        <span className="text-sm text-muted-foreground italic">No description</span>
                      )}
                    </div>

                    {/* Date Uploaded */}
                    <div className="col-span-1 flex items-center cursor-pointer" onClick={handleRowClick}>
                      <TooltipProvider>
                        <Tooltip delayDuration={300}>
                          <TooltipTrigger asChild>
                            <span className="text-sm text-muted-foreground">
                              {format(new Date(doc.metadata.created_at), "MMM d")}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="top">
                            <p className="text-sm">
                              {format(new Date(doc.metadata.created_at), "MMMM d, yyyy 'at' h:mm a")}
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>

                    {/* Actions */}
                    <div className="col-span-2 flex items-center justify-end">
                      <AlertDialog>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-foreground"
                              disabled={deletingDocumentId === doc.metadata.file_id || batchDeleting}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setEditDocumentId(doc.metadata.file_id)}
                              disabled={deletingDocumentId === doc.metadata.file_id || batchDeleting}
                            >
                              <Edit className="mr-2 h-4 w-4" />
                              Edit Title & Description
                            </DropdownMenuItem>

                            {/* Download submenu */}
                            <DownloadFormatMenu open={downloadFormatMenu === doc.metadata.file_id} onOpenChange={(open) => setDownloadFormatMenu(open ? doc.metadata.file_id : null)}>
                              <DownloadFormatTrigger asChild>
                                <DropdownMenuItem
                                  disabled={downloadingDocumentId === doc.metadata.file_id || batchDeleting}
                                  onSelect={(e) => e.preventDefault()}
                                >
                                  <Download className="mr-2 h-4 w-4" />
                                  {downloadingDocumentId === doc.metadata.file_id ? "Downloading..." : "Download"}
                                  <span className="ml-auto text-xs text-muted-foreground">▶</span>
                                </DropdownMenuItem>
                              </DownloadFormatTrigger>
                              <DownloadFormatContent align="start" side="right">
                                <DownloadFormatItem
                                  onClick={() => handleDownloadDocument(doc.metadata.file_id, doc.metadata.name, "md")}
                                  disabled={downloadingDocumentId === doc.metadata.file_id}
                                >
                                  Markdown (.md)
                                </DownloadFormatItem>
                                <DownloadFormatItem
                                  onClick={() => handleDownloadDocument(doc.metadata.file_id, doc.metadata.name, "docx")}
                                  disabled={downloadingDocumentId === doc.metadata.file_id}
                                >
                                  Word Document (.docx)
                                </DownloadFormatItem>
                              </DownloadFormatContent>
                            </DownloadFormatMenu>

                            <AlertDialogTrigger asChild>
                              <DropdownMenuItem
                                className="text-destructive"
                                disabled={actionsDisabled || deletingDocumentId === doc.metadata.file_id || batchDeleting}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                {deletingDocumentId === doc.metadata.file_id ? "Deleting..." : "Delete"}
                              </DropdownMenuItem>
                            </AlertDialogTrigger>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle className="text-lg font-medium">
                              Delete Document
                            </AlertDialogTitle>
                            <AlertDialogDescription className="text-sm text-muted-foreground">
                              Are you sure you want to delete
                              <span className="font-medium text-foreground">
                                {" "}
                                "{doc.metadata.name}"
                              </span>
                              ? This action cannot be undone and will permanently remove the document from your collection.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel 
                              className="text-sm"
                              disabled={deletingDocumentId === doc.metadata.file_id}
                            >
                              Cancel
                            </AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => 
                                await handleDeleteDocument(doc.metadata.file_id, doc.metadata.name)
                              }
                              className="bg-destructive hover:bg-destructive/90 text-white text-sm"
                              disabled={actionsDisabled || deletingDocumentId === doc.metadata.file_id}
                            >
                              {deletingDocumentId === doc.metadata.file_id ? "Deleting..." : "Delete Document"}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                );
              })}

              {/* Load More Trigger */}
              {hasMore && !searchTerm && (
                <div 
                  ref={loadMoreTriggerRef}
                  className="flex items-center justify-center py-4"
                >
                  {loadingMore ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading more documents...
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground">
                      Scroll to load more documents
                    </div>
                  )}
                </div>
              )}

              {/* Search active notice for infinite scroll */}
              {searchTerm && hasMore && (
                <div className="flex items-center justify-center py-4 text-xs text-muted-foreground">
                  Clear search to load more documents
                </div>
              )}

              {/* Initial Loading State */}
              {loading && processedDocuments.length === 0 && (
                <div className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading documents...
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Batch Delete Confirmation Dialog */}
        <AlertDialog open={showBatchDeleteDialog} onOpenChange={setShowBatchDeleteDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="text-lg font-medium">
                Delete {selectedDocuments.size} Documents
              </AlertDialogTitle>
              <AlertDialogDescription asChild>
                <div className="text-sm text-muted-foreground">
                  Are you sure you want to delete {selectedDocuments.size} selected document{selectedDocuments.size === 1 ? '' : 's'}?
                  {selectedDocumentDetails.length > 0 && (
                    <div className="mt-3 p-3 bg-muted rounded-md">
                      <div className="text-xs font-medium text-foreground mb-2">Documents to be deleted:</div>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {selectedDocumentDetails.slice(0, 5).map(doc => (
                          <div key={doc.metadata.file_id} className="text-xs text-muted-foreground">
                            • {doc.metadata.name}
                          </div>
                        ))}
                        {selectedDocumentDetails.length > 5 && (
                          <div className="text-xs text-muted-foreground font-medium">
                            ... and {selectedDocumentDetails.length - 5} more
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  <div className="mt-3 text-sm font-medium text-destructive">
                    This action cannot be undone and will permanently remove these documents from your collection.
                  </div>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={batchDeleting}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleBatchDelete}
                className="bg-destructive hover:bg-destructive/90 text-white"
                disabled={batchDeleting}
              >
                {batchDeleting ? "Deleting..." : `Delete ${selectedDocuments.size} Documents`}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Edit Document Dialog */}
        {editDocumentId && (() => {
          const doc = documents.find(d => d.metadata.file_id === editDocumentId);
          if (!doc) return null;
          
          return (
            <EditDocumentDialog
              documentId={editDocumentId}
              collectionId={selectedCollection.uuid}
              currentTitle={doc.metadata.name || doc.metadata.title || ""}
              currentDescription={doc.metadata.description || ""}
              open={!!editDocumentId}
              onOpenChange={(open: boolean) => !open && setEditDocumentId(null)}
              onSuccess={async () => {
                // Refresh documents after successful edit
                if (onDocumentsChanged) {
                  await onDocumentsChanged();
                }
              }}
            />
          );
        })()}
      </div>
    </div>
  );
}
