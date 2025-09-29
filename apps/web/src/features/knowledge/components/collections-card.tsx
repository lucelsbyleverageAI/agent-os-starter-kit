"use client";

import type React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useKnowledgeContext } from "../providers/Knowledge";
import type { Collection } from "@/types/collection";
import type { ShareAtCreation } from "@/types/user";
import { useState } from "react";
import { CollectionsList } from "./collections-list";
import { notify } from "@/utils/toast";
import { knowledgeMessages } from "@/utils/toast-messages";
import { toast } from "sonner";
import { CreateCollectionDialog } from "./create-collection-dialog";
import { Skeleton } from "@/components/ui/skeleton";

interface CollectionsCardProps {
  selectedCollection: Collection | undefined;
  setSelectedCollection: React.Dispatch<
    React.SetStateAction<Collection | undefined>
  >;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
}

export function CollectionsCard({
  selectedCollection,
  setSelectedCollection,
  setCurrentPage,
}: CollectionsCardProps) {
  const {
    collections,
    createCollectionWithSharing,
    deleteCollection,
    listDocuments,
    setDocuments,
    updateCollection,
  } = useKnowledgeContext();

  const [open, setOpen] = useState(false);

  // State for pagination
  const [collectionsCurrentPage, setCollectionsCurrentPage] = useState(1);
  const collectionsItemsPerPage = 5;

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
      setOpen(false);
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

  // Handle deleting a collection (uses collection hook and document hook)
  const handleDeleteCollection = async (id: string) => {
    const result = await deleteCollection(id);
    
    if (result.ok) {
      const message = knowledgeMessages.collection.delete.success();
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
      
      // If we just deleted the currently selected collection, select a new one
      if (selectedCollection?.uuid === id) {
        // Filter out the deleted collection from the current collections
        const remainingCollections = collections.filter((c) => c.uuid !== id);
        
        if (remainingCollections.length === 0) {
          setSelectedCollection(undefined);
          setDocuments([]);
          return;
        }
        
        // Select the first remaining collection
        const newSelectedCollection = remainingCollections[0];
        setSelectedCollection(newSelectedCollection);
        setCurrentPage(1); // Reset document page
        
        try {
          const docs = await listDocuments(newSelectedCollection.uuid);
          setDocuments(docs);
        } catch (docError) {
          console.error("Failed to fetch documents for new collection:", docError);
          // Don't throw here - collection deletion was successful
          setDocuments([]);
          notify.warning("Collection deleted", {
            description: "Failed to load documents for the new selection.",
            key: "collection:delete:warning",
          });
        }
      }
    } else {
      const message = knowledgeMessages.collection.delete.error();
      notify.error(message.title, {
        description: result.errorMessage,
        key: message.key,
      });
    }
  };

  const handleUpdateCollection = async (
    id: string,
    name: string,
    metadata: Record<string, any>,
  ) => {
    const loadingToast = toast.loading("Updating collection", {
      richColors: true,
    });
    await updateCollection(id, name, metadata);
    toast.dismiss(loadingToast);
    toast.success("Collection updated successfully", { richColors: true });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Collections</CardTitle>
        <CreateCollectionDialog
          open={open}
          onOpenChange={setOpen}
          onSubmit={handleCreateCollection}
        />
      </CardHeader>
      <CardContent>
        <CollectionsList
          collections={collections}
          selectedCollection={selectedCollection}
          onSelect={async (id) => {
            if (selectedCollection?.uuid === id) {
              return;
            }
            
            // Find the collection in the current state
            const targetCollection = collections.find((c) => c.uuid === id);
            if (!targetCollection) {
              console.warn(`Collection with ID ${id} not found in current state`);
              toast.error("Collection not found", {
                richColors: true,
                description: "The selected collection may have been deleted"
              });
              return;
            }
            
            setSelectedCollection(targetCollection);
            setCurrentPage(1); // Reset page when collection changes
            setCollectionsCurrentPage(1);
            
            try {
              const documents = await listDocuments(id);
              setDocuments(documents);
            } catch (error) {
              console.error("Failed to fetch documents for collection:", error);
              toast.error("Failed to fetch documents", {
                richColors: true,
                description: error instanceof Error ? error.message : "Unknown error"
              });
              setDocuments([]); // Clear documents on error
            }
          }}
          onDelete={(id) => handleDeleteCollection(id)}
          onEdit={handleUpdateCollection}
          currentPage={collectionsCurrentPage}
          itemsPerPage={collectionsItemsPerPage}
          totalCollections={collections.length}
          onPageChange={setCollectionsCurrentPage}
        />
      </CardContent>
    </Card>
  );
}

export function CollectionsCardLoading() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="size-8" />
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton
              key={index}
              className="h-8 w-full"
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
