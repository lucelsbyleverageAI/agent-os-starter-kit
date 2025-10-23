"use client";

import React, { use, useEffect, useState } from "react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { AppHeader } from "@/components/app-header";
import { PageHeader } from "@/components/ui/page-header";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { Files, ArrowLeft } from "lucide-react";
import { useKnowledgeContext } from "@/features/knowledge/providers/Knowledge";
import { CollectionPageContent } from "@/features/knowledge/components/collection-page-content";
import { getCollectionName } from "@/features/knowledge/hooks/use-knowledge";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";

interface CollectionPageProps {
  params: Promise<{
    collectionId: string;
  }>;
}

/**
 * Dedicated page for viewing and managing a knowledge collection.
 * Accessible at /knowledge/[collectionId]
 */
export default function CollectionPage({ params }: CollectionPageProps): React.ReactNode {
  const { collectionId } = use(params);
  const router = useRouter();
  const { collections, initialSearchExecuted } = useKnowledgeContext();
  const [collection, setCollection] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Find the collection from context
  useEffect(() => {
    if (initialSearchExecuted) {
      const found = collections.find(c => c.uuid === collectionId);
      setCollection(found || null);
      setLoading(false);
    }
  }, [collectionId, collections, initialSearchExecuted]);

  // Loading state
  if (loading || !initialSearchExecuted) {
    return (
      <React.Suspense fallback={<div>Loading...</div>}>
        <AppHeader>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/knowledge">Knowledge</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Loading...</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </AppHeader>

        <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
          <div className="space-y-4">
            <Skeleton className="h-12 w-64" />
            <Skeleton className="h-4 w-96" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </React.Suspense>
    );
  }

  // Collection not found
  if (!collection) {
    return (
      <React.Suspense fallback={<div>Loading...</div>}>
        <AppHeader>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/knowledge">Knowledge</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Not Found</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </AppHeader>

        <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
          <div className="flex flex-col items-center justify-center gap-4 py-12">
            <h2 className="text-2xl font-semibold">Collection Not Found</h2>
            <p className="text-muted-foreground">
              The collection you're looking for doesn't exist or you don't have access to it.
            </p>
            <Button onClick={() => router.push("/knowledge")} variant="outline">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Knowledge
            </Button>
          </div>
        </div>
      </React.Suspense>
    );
  }

  const collectionName = getCollectionName(collection.name);
  const documentCount = collection.document_count || 0;

  return (
    <React.Suspense fallback={<div>Loading...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/knowledge">Knowledge</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{collectionName}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>

      <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
        <div className="mb-6">
          <Button
            onClick={() => router.push("/knowledge")}
            variant="ghost"
            size="sm"
            className="mb-4"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Collections
          </Button>

          <PageHeader
            title={collectionName}
            description={
              collection.metadata?.description ||
              "Manage documents in this knowledge collection"
            }
            badge={
              <MinimalistBadgeWithText
                icon={Files}
                text={`${documentCount} document${documentCount !== 1 ? 's' : ''}`}
              />
            }
          />
        </div>

        <div className="mt-6">
          <CollectionPageContent collection={collection} />
        </div>
      </div>
    </React.Suspense>
  );
}
