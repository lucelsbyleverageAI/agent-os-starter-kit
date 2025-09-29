"use client";

import React, { useState } from "react";
import { Card, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { MinimalistBadge, MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import type { Collection } from "@/types/collection";
import {
  DEFAULT_COLLECTION_NAME,
  getCollectionName,
} from "../hooks/use-knowledge";
import { useKnowledgeContext } from "../providers/Knowledge";
import { CollectionActions } from "./collections-list/collection-actions";
import { Crown, Edit, Eye, FileText, Files } from "lucide-react";
import { notify } from "@/utils/toast";
import { knowledgeMessages } from "@/utils/toast-messages";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentsModal } from "./documents-modal";

// Permission icon mapping
function getPermissionIconAndTooltip(permissionLevel?: string) {
  switch (permissionLevel) {
    case "owner":
      return {
        icon: Crown,
        tooltip: "Owner - Full access and management permissions",
      };
    case "editor":
      return {
        icon: Edit,
        tooltip: "Editor - Can view, add, and delete documents",
      };
    case "viewer":
      return {
        icon: Eye,
        tooltip: "Viewer - Can only view documents",
      };
    default:
      return {
        icon: Eye,
        tooltip: "View access",
      };
  }
}

interface CollectionCardProps {
  collection: Collection;
}

export function CollectionCard({ collection }: CollectionCardProps) {
  const [documentsModalOpen, setDocumentsModalOpen] = useState(false);
  const { deleteCollection, updateCollection } = useKnowledgeContext();
  
  const permissionDisplay = getPermissionIconAndTooltip(collection.permission_level);

  const handleDeleteCollection = async (collectionId: string) => {
    const result = await deleteCollection(collectionId);
    
    if (result.ok) {
      const message = knowledgeMessages.collection.delete.success();
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
    } else {
      const message = knowledgeMessages.collection.delete.error();
      notify.error(message.title, {
        description: result.errorMessage,
        key: message.key,
      });
    }
  };

  const handleEditCollection = async (
    collectionId: string,
    name: string,
    metadata: Record<string, any>,
  ) => {
    await updateCollection(collectionId, name, metadata);
  };

  const handleCardClick = () => {
    setDocumentsModalOpen(true);
  };

  const handleManageDocumentsClick = () => {
    setDocumentsModalOpen(true);
  };
  
  return (
    <>
      <Card 
        className="overflow-hidden relative group h-44 flex flex-col transition-all duration-300 ease-out vibrate-on-hover hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10 cursor-pointer"
        onClick={handleCardClick}
      >
        {/* Fixed Header - Small portion at top */}
        <CardHeader className="px-6 h-3 flex-shrink-0 flex items-center">
          <div className="flex items-center justify-between gap-3 w-full">
            <CardTitle className="text-sm font-medium text-foreground min-w-0 flex-1">
              {/* Collection Name - truncate with ellipses */}
              <span className="truncate">{getCollectionName(collection.name)}</span>
            </CardTitle>

            {/* Three-dots menu - always in same position */}
            {collection.name !== DEFAULT_COLLECTION_NAME && (
              <div 
                className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <CollectionActions
                  collection={collection}
                  onDelete={handleDeleteCollection}
                  onEdit={handleEditCollection}
                />
              </div>
            )}
          </div>
        </CardHeader>
        
        {/* Description Area - Controlled middle space */}
        <div className="px-6 flex-1 min-h-0 -mt-1">
          {collection.metadata?.description &&
          typeof collection.metadata.description === "string" ? (
            <p className="text-muted-foreground text-sm leading-5 overflow-hidden text-ellipsis" 
               style={{ 
                 display: '-webkit-box', 
                 WebkitLineClamp: 3, 
                 WebkitBoxOrient: 'vertical' 
               }}>
              {collection.metadata.description}
            </p>
          ) : (
            <p className="text-muted-foreground/50 text-sm italic">No description</p>
          )}
        </div>
        
        {/* Fixed Footer - Small portion at bottom */}
        <CardFooter className="flex w-full justify-between items-center h-3 px-6 flex-shrink-0">
          {/* Left side: Permission badge and document count */}
          <div className="flex items-center gap-2">
            <MinimalistBadge
              icon={permissionDisplay.icon}
              tooltip={permissionDisplay.tooltip}
            />
            <MinimalistBadgeWithText
              icon={Files}
              tooltip={`${collection.document_count || 0} documents in this collection`}
              text={`${collection.document_count || 0}`}
            />
          </div>

          {/* Right side: Manage Documents button */}
          <div 
            className="flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            <MinimalistIconButton
              icon={FileText}
              tooltip="Manage Documents"
              onClick={handleManageDocumentsClick}
            />
          </div>
        </CardFooter>
      </Card>

      {/* Documents Modal */}
      <DocumentsModal
        open={documentsModalOpen}
        onOpenChange={setDocumentsModalOpen}
        collection={collection}
      />
    </>
  );
}

export function CollectionCardLoading() {
  return (
    <Card className="overflow-hidden h-44 flex flex-col">
      <CardHeader className="px-6 h-3 flex-shrink-0 flex items-center">
        <div className="flex items-center justify-between gap-3 w-full">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-6 w-6" />
        </div>
      </CardHeader>
      
      <div className="px-6 flex-1 min-h-0 -mt-1 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
      
      <CardFooter className="flex w-full justify-between items-center h-3 px-6 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-6" />
          <Skeleton className="h-6 w-12" />
        </div>
        <Skeleton className="h-6 w-6" />
      </CardFooter>
    </Card>
  );
} 