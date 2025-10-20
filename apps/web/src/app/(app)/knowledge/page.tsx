"use client";

import KnowledgeInterface from "@/features/knowledge";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

import { PageHeader } from "@/components/ui/page-header";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { useKnowledgeContext } from "@/features/knowledge/providers/Knowledge";
import { CreateCollectionDialog } from "@/features/knowledge/components/create-collection-dialog";
import { Hash, FolderPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ShareAtCreation } from "@/types/user";
import React, { useState } from "react";
import { AppHeader } from "@/components/app-header";

/**
 * The /knowledge page.
 * Contains the interface for interacting with the Knowledge system.
 */
export default function KnowledgePage(): React.ReactNode {
  const { collections, initialSearchExecuted, createCollectionWithSharing } = useKnowledgeContext();
  const [showCreateCollectionDialog, setShowCreateCollectionDialog] = useState(false);
  
  const collectionsCount = collections.length;

  // Handle creating a new collection with optional sharing
  const handleCreateCollection = async (
    name: string, 
    description: string, 
    shareWith?: ShareAtCreation[]
  ) => {
    const loadingToast = toast.loading(
      shareWith && shareWith.length > 0 
        ? "Creating and sharing collection" 
        : "Creating collection", 
      {
        richColors: true,
      }
    );
    
    const success = await createCollectionWithSharing(name, {
      description,
    }, shareWith);
    
    toast.dismiss(loadingToast);
    
    if (success) {
      setShowCreateCollectionDialog(false);
      // Success message is handled by the createCollectionWithSharing function
    } else {
      toast.warning(
        `Collection named '${name}' could not be created (likely already exists).`,
        {
          duration: 5000,
          richColors: true,
        },
      );
    }
  };

  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Knowledge</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      
      <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
        <PageHeader
          title="Knowledge"
          description="Manage the knowledge bases of your agents"
          badge={
            initialSearchExecuted && (
              <MinimalistBadgeWithText
                icon={Hash}
                text={`${collectionsCount} collection${collectionsCount !== 1 ? 's' : ''}`}
              />
            )
          }
          action={
            <Button onClick={() => setShowCreateCollectionDialog(true)}>
              <FolderPlus className="mr-2 h-4 w-4" />
              Create Collection
            </Button>
          }
        />
        
        <div className="mt-6">
          <KnowledgeInterface />
        </div>
      </div>

      <CreateCollectionDialog
        open={showCreateCollectionDialog}
        onOpenChange={setShowCreateCollectionDialog}
        onSubmit={handleCreateCollection}
      />
    </React.Suspense>
  );
}
