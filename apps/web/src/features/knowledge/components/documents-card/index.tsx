"use client";

import type React from "react";
import { useState, useMemo } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "next/navigation";
import type { Collection } from "@/types/collection";
import { useKnowledgeContext } from "../../providers/Knowledge";
import { EnhancedUploadDialog, UploadData } from "../enhanced-upload-dialog";
import { JobProgressCard } from "../job-progress-card";
import { DocumentsTable } from "./documents-table";

interface DocumentsCardProps {
  selectedCollection: Collection | undefined;
  currentPage: number;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
}

export function DocumentsCard({
  selectedCollection,
  currentPage,
  setCurrentPage,
}: DocumentsCardProps) {
  const _toast = toast;
  const _router = useRouter();
  const {
    documents,
    handleEnhancedUpload,
    processingJobs,
    cancelJob,
  } = useKnowledgeContext();

  const itemsPerPage = 10;

  const [enhancedUploadOpen, setEnhancedUploadOpen] = useState(false);

  const filteredDocuments = useMemo(
    () =>
      documents.filter(
        (doc) => doc.metadata.collection === selectedCollection?.uuid,
      ),
    [documents, selectedCollection],
  );

  // Calculate pagination for documents
  const totalPages = Math.ceil(filteredDocuments.length / itemsPerPage);
  const currentDocuments = useMemo(
    () =>
      filteredDocuments.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage,
      ),
    [filteredDocuments, currentPage, itemsPerPage],
  );

  // Handle enhanced upload
  const handleEnhancedUploadSubmit = async (uploadData: UploadData) => {
    if (!selectedCollection) {
      throw new Error("No collection selected");
    }

    await handleEnhancedUpload(uploadData, selectedCollection.uuid);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2">
          <CardTitle>
            {selectedCollection?.name}
          </CardTitle>
          <CardDescription>
            {selectedCollection?.metadata?.description || "No description available"}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {/* Enhanced Upload Button */}
        <div className="mb-6 flex flex-col items-center">
          <div className="w-full max-w-xs">
            <Button 
              onClick={() => setEnhancedUploadOpen(true)}
              disabled={!selectedCollection}
              className="w-full max-w-xs"
              size="lg"
            >
              <Plus className="mr-2 h-4 w-4" />
              Upload Documents
            </Button>
          </div>
          <p className="text-sm text-gray-500 mt-2 text-center">
            Upload files, URLs, or text content to this collection.
          </p>
        </div>

        {/* Job Progress */}
        {selectedCollection && processingJobs.length > 0 && (
          <div className="mb-6">
            <JobProgressCard 
              jobs={processingJobs}
              collectionId={selectedCollection.uuid}
              onCancelJob={cancelJob}
              compact={false}
            />
          </div>
        )}

        {/* Document Table */}
        {selectedCollection && (
          <DocumentsTable
            documents={currentDocuments}
            selectedCollection={selectedCollection}
            actionsDisabled={false}
          />
        )}

        {/* Pagination */}
        {filteredDocuments.length > itemsPerPage && (
          <Pagination className="mt-4">
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    setCurrentPage(Math.max(1, currentPage - 1));
                  }}
                  aria-disabled={currentPage === 1}
                  className={
                    currentPage === 1
                      ? "text-muted-foreground pointer-events-none"
                      : undefined
                  }
                />
              </PaginationItem>
              {[...Array(totalPages)].map((_, page) => (
                <PaginationItem key={page + 1}>
                  <PaginationLink
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setCurrentPage(page + 1);
                    }}
                    isActive={currentPage === page + 1}
                  >
                    {page + 1}
                  </PaginationLink>
                </PaginationItem>
              ))}
              <PaginationItem>
                <PaginationNext
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    setCurrentPage(Math.min(totalPages, currentPage + 1));
                  }}
                  aria-disabled={currentPage === totalPages}
                  className={
                    currentPage === totalPages
                      ? "text-muted-foreground pointer-events-none"
                      : undefined
                  }
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        )}
      </CardContent>

      {/* Enhanced Upload Dialog */}
      <EnhancedUploadDialog
        open={enhancedUploadOpen}
        onOpenChange={setEnhancedUploadOpen}
        onSubmit={handleEnhancedUploadSubmit}
        collectionId={selectedCollection?.uuid || ""}
      />
    </Card>
  );
}

export function DocumentsCardLoading() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-6 w-48" />
      </CardHeader>
      <CardContent>
        <div className="mb-6 flex flex-col gap-6">
          <div className="flex items-center justify-start gap-2">
            <Skeleton className="h-6 w-22" />
            <Skeleton className="h-6 w-22" />
          </div>
          <Skeleton className="h-38 w-full" />
          <div className="flex flex-col gap-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton
                key={index}
                className="h-8 w-full"
              />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
