"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { useKnowledgeContext } from "../providers/Knowledge";
import { DocumentsTable } from "./documents-card/documents-table";
import { Collection } from "@/types/collection";
import { EnhancedUploadDialog, type UploadData } from "./enhanced-upload-dialog";
import { JobProgressCard } from "./job-progress-card";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { Document } from "@langchain/core/documents";
import { toast } from "sonner";
import { useSearchParams } from "next/navigation";

interface CollectionPageContentProps {
  collection: Collection;
}

/**
 * Collection page content showing documents table and upload functionality.
 * Extracted from DocumentsModal to be used in dedicated collection pages.
 */
export function CollectionPageContent({ collection }: CollectionPageContentProps) {
  const searchParams = useSearchParams();
  const {
    listDocuments,
    handleEnhancedUpload,
    processingJobs,
    cancelJob,
    refreshCollectionDocumentCount,
  } = useKnowledgeContext();

  const [enhancedUploadOpen, setEnhancedUploadOpen] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [currentOffset, setCurrentOffset] = useState(0);
  const itemsPerPage = 20; // Load 20 documents at a time

  // Track completed job IDs to prevent duplicate refreshes
  const completedJobIds = useRef<Set<string>>(new Set());

  // Load initial documents for this collection
  useEffect(() => {
    if (collection.uuid) {
      const loadInitialDocuments = async () => {
        setDocumentsLoading(true);
        setDocuments([]);
        setCurrentOffset(0);
        setHasMore(true);

        try {
          // Force fresh data if we have a refresh parameter
          const refreshParam = searchParams.get('refresh');
          const docs = await listDocuments(collection.uuid, {
            limit: itemsPerPage,
            offset: 0,
            useCache: refreshParam ? false : undefined
          });
          setDocuments(docs);
          setCurrentOffset(itemsPerPage);

          // If we got fewer documents than requested, we've reached the end
          if (docs.length < itemsPerPage) {
            setHasMore(false);
          }

          // Refresh collection document count if we're doing a forced refresh
          if (refreshParam) {
            await refreshCollectionDocumentCount(collection.uuid);
          }
        } catch (_error) {
          console.error('Failed to load documents:', _error);
          setDocuments([]);
          setHasMore(false);
        } finally {
          setDocumentsLoading(false);
        }
      };

      loadInitialDocuments();
    }
  }, [collection.uuid, listDocuments, searchParams, refreshCollectionDocumentCount]);

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
      setDocuments(prev => [...prev, ...newDocs]);
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
        limit: Math.max(itemsPerPage, documents.length),
        offset: 0,
        useCache: false // Force fresh data
      });

      setDocuments(docs);
      setCurrentOffset(docs.length);
      setHasMore(docs.length >= itemsPerPage);

      // Refresh the collection's document count badge
      await refreshCollectionDocumentCount(collection.uuid);

    } catch (_error) {
      toast.error("Failed to refresh documents", {
        description: "Please try reloading the page"
      });
    } finally {
      setDocumentsLoading(false);
    }
  }, [collection.uuid, listDocuments, documents.length, refreshCollectionDocumentCount]);

  // Memoize filtered collection jobs to prevent unnecessary re-renders
  const collectionJobs = useMemo(() =>
    processingJobs.filter(job => job.collection_id === collection.uuid),
    [processingJobs, collection.uuid]
  );

  // Watch for job completion and refresh documents (optimized to prevent duplicate refreshes)
  useEffect(() => {
    const newlyCompletedJobs = collectionJobs.filter(job =>
      job.status === 'completed' &&
      job.documents_processed > 0 &&
      !completedJobIds.current.has(job.id)
    );

    if (newlyCompletedJobs.length > 0) {
      // Mark these jobs as processed
      newlyCompletedJobs.forEach(job => completedJobIds.current.add(job.id));

      // Refresh documents once for all newly completed jobs
      refreshDocuments();
    }
  }, [collectionJobs, refreshDocuments]);

  // Handle document deletion - refresh the document list
  const handleDocumentDeleted = async () => {
    try {
      // Force fresh data by bypassing cache after deletion
      const docs = await listDocuments(collection.uuid, {
        limit: Math.max(itemsPerPage, documents.length),
        offset: 0,
        useCache: false // Force fresh data after deletion
      });

      setDocuments(docs);
      setCurrentOffset(docs.length);
      setHasMore(docs.length >= itemsPerPage);

      // Refresh the collection's document count badge
      await refreshCollectionDocumentCount(collection.uuid);

    } catch (_error) {
      toast.error("Failed to refresh documents", {
        description: "Please try reloading the page"
      });
    }
  };

  return (
    <>
      <div className="flex flex-col gap-4">
        {/* Enhanced Upload Button */}
        <div className="flex justify-center pt-2">
          <Button
            onClick={() => setEnhancedUploadOpen(true)}
            className="w-full max-w-xs"
            size="lg"
          >
            <Plus className="mr-2 h-4 w-4" />
            Add To This Collection
          </Button>
        </div>

        {/* Job Progress */}
        {collectionJobs.length > 0 && (
          <div className="px-1">
            <JobProgressCard
              jobs={collectionJobs}
              onCancelJob={cancelJob}
              compact={false}
            />
          </div>
        )}

        {/* Document Table with Infinite Scroll */}
        <div className={cn("flex-1 min-h-0", ...getScrollbarClasses('y'))}>
          <DocumentsTable
            documents={documents}
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
