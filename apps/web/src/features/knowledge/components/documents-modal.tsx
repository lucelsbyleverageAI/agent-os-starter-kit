"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { useKnowledgeContext } from "../providers/Knowledge";
import { DocumentsTable } from "./documents-card/documents-table";
import { Collection } from "@/types/collection";
import { getCollectionName } from "../hooks/use-knowledge";
import { EnhancedUploadDialog, type UploadData } from "./enhanced-upload-dialog";
import { JobProgressCard } from "./job-progress-card";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { Document } from "@langchain/core/documents";
import { toast } from "sonner";

interface DocumentsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collection: Collection;
}

export function DocumentsModal({
  open,
  onOpenChange,
  collection,
}: DocumentsModalProps) {
  const {
    listDocuments,
    handleEnhancedUpload,
    processingJobs,
    cancelJob,
    refreshCollectionDocumentCount,
  } = useKnowledgeContext();

  const [enhancedUploadOpen, setEnhancedUploadOpen] = useState(false);
  const [modalDocuments, setModalDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [currentOffset, setCurrentOffset] = useState(0);
  const itemsPerPage = 20; // Load 20 documents at a time

  // Load initial documents for this specific collection when modal opens
  useEffect(() => {
    if (open && collection.uuid) {
      const loadInitialDocuments = async () => {
        setDocumentsLoading(true);
        setModalDocuments([]);
        setCurrentOffset(0);
        setHasMore(true);
        
        try {
          const docs = await listDocuments(collection.uuid, { 
            limit: itemsPerPage, 
            offset: 0 
          });
                    setModalDocuments(docs);
          setCurrentOffset(itemsPerPage);
          
          // If we got fewer documents than requested, we've reached the end
          if (docs.length < itemsPerPage) {
            setHasMore(false);
          }
        } catch (_error) {
          console.error('Failed to load documents for modal:', _error);
          setModalDocuments([]);
          setHasMore(false);
        } finally {
          setDocumentsLoading(false);
        }
      };
      
      loadInitialDocuments();
    } else if (!open) {
      // Clear documents when modal closes to free memory
      setModalDocuments([]);
      setCurrentOffset(0);
      setHasMore(true);
    }
  }, [open, collection.uuid, listDocuments]);

  // Load more documents for infinite scroll
  const handleLoadMore = useCallback(async () => {
    if (!hasMore || documentsLoading) return;

    try {
            const newDocs = await listDocuments(collection.uuid, { 
        limit: itemsPerPage, 
        offset: currentOffset 
      });
            
      if (newDocs.length === 0) {
        setHasMore(false);
        return;
      }
      
      // Append new documents to existing ones
      setModalDocuments(prev => [...prev, ...newDocs]);
      setCurrentOffset(prev => prev + itemsPerPage);
      
      // If we got fewer documents than requested, we've reached the end
      if (newDocs.length < itemsPerPage) {
        setHasMore(false);
      }
    } catch (_error) {
      console.error('Failed to load more documents:', _error);
      toast.error("Failed to load more documents", {
        richColors: true,
        description: "Please try scrolling again"
      });
    }
  }, [collection.uuid, currentOffset, hasMore, documentsLoading, listDocuments]);

  // Handle enhanced upload
  const handleEnhancedUploadSubmit = async (uploadData: UploadData) => {
    await handleEnhancedUpload(uploadData, collection.uuid);
    
    // Close the upload dialog immediately after starting the job
    setEnhancedUploadOpen(false);
    
    // Note: Document refresh will happen when jobs complete successfully
    // via the job completion effect below
  };

  // Generic function to refresh documents
  const refreshDocuments = useCallback(async () => {
    try {
      setDocumentsLoading(true);
      
      // Force fresh data by bypassing cache when refreshing
      const docs = await listDocuments(collection.uuid, { 
        limit: Math.max(itemsPerPage, modalDocuments.length), 
        offset: 0,
        useCache: false // Force fresh data
      });
      
      setModalDocuments(docs);
      setCurrentOffset(docs.length);
      setHasMore(docs.length >= itemsPerPage);
      
      // Refresh the collection's document count badge
      await refreshCollectionDocumentCount(collection.uuid);
      
    } catch (_error) {
      toast.error("Failed to refresh documents", {
        description: "Please close and reopen the modal"
      });
    } finally {
      setDocumentsLoading(false);
    }
  }, [collection.uuid, listDocuments, modalDocuments.length, refreshCollectionDocumentCount]);

  // Watch for job completion and refresh documents
  useEffect(() => {
    const collectionJobs = processingJobs.filter(job => job.collection_id === collection.uuid);
    const justCompletedJobs = collectionJobs.filter(job => 
      job.status === 'completed' && 
      job.documents_processed > 0
    );
    
    if (justCompletedJobs.length > 0) {
            refreshDocuments();
    }
  }, [processingJobs, collection.uuid, refreshDocuments]);

  // Handle document deletion - refresh the modal's document list
  const handleDocumentDeleted = async () => {
    try {
      // Force fresh data by bypassing cache after deletion
      const docs = await listDocuments(collection.uuid, { 
        limit: Math.max(itemsPerPage, modalDocuments.length), 
        offset: 0,
        useCache: false // Force fresh data after deletion
      });
      
      setModalDocuments(docs);
      setCurrentOffset(docs.length);
      setHasMore(docs.length >= itemsPerPage);
      
      // Refresh the collection's document count badge
      await refreshCollectionDocumentCount(collection.uuid);
      
    } catch (_error) {
      toast.error("Failed to refresh documents", {
        description: "Please close and reopen the modal"
      });
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={cn("!max-w-6xl !w-[85vw] max-h-[90vh] flex flex-col", ...getScrollbarClasses('y'))}>
          <DialogHeader className="flex-shrink-0">
            <DialogTitle className="text-xl">
              {getCollectionName(collection.name)}
            </DialogTitle>
            <p className="text-sm text-muted-foreground">
              {collection.metadata?.description || "No description available"}
            </p>
          </DialogHeader>

          <div className="flex-1 min-h-0 space-y-6">
            {/* Enhanced Upload Button */}
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs">
                <Button 
                  onClick={() => setEnhancedUploadOpen(true)}
                  className="w-full max-w-xs"
                  size="lg"
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add To This Collection
                </Button>
              </div>
            </div>

            {/* Job Progress */}
            {processingJobs.length > 0 && (
              <div>
                <JobProgressCard 
                  jobs={processingJobs}
                  collectionId={collection.uuid}
                  onCancelJob={cancelJob}
                  compact={false}
                />
              </div>
            )}

            {/* Document Table with Infinite Scroll */}
            <div className={cn("flex-1 min-h-0 pb-6", ...getScrollbarClasses('y'))}>
              <DocumentsTable
                documents={modalDocuments}
                selectedCollection={collection}
                actionsDisabled={false}
                onDocumentDeleted={handleDocumentDeleted}
                onDocumentsChanged={refreshDocuments}
                onLoadMore={handleLoadMore}
                hasMore={hasMore}
                loading={documentsLoading}
                totalDocumentCount={collection.document_count}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Enhanced Upload Dialog */}
      <EnhancedUploadDialog
        open={enhancedUploadOpen}
        onOpenChange={setEnhancedUploadOpen}
        onSubmit={handleEnhancedUploadSubmit}
        collectionId={collection.uuid}
      />
    </>
  );
} 