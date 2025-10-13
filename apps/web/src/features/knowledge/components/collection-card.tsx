"use client";

import React from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MinimalistBadge, MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import type { Collection } from "@/types/collection";
import {
  DEFAULT_COLLECTION_NAME,
  getCollectionName,
} from "../hooks/use-knowledge";
import { useKnowledgeContext } from "../providers/Knowledge";
import { CollectionActions } from "./collections-list/collection-actions";
import { Crown, Edit, Eye, BookOpen, Files } from "lucide-react";
import { notify } from "@/utils/toast";
import { knowledgeMessages } from "@/utils/toast-messages";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "next/navigation";

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
  const router = useRouter();
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
    router.push(`/knowledge/${collection.uuid}`);
  };

  const handleManageDocumentsClick = () => {
    router.push(`/knowledge/${collection.uuid}`);
  };
  
  return (
    <>
      <Card
        className="group relative flex flex-col items-start gap-3 p-6 transition-all hover:border-primary hover:shadow-md vibrate-on-hover cursor-pointer"
        onClick={handleCardClick}
      >
        {/* Three-dots menu - absolute positioned in top-right */}
        {collection.name !== DEFAULT_COLLECTION_NAME && (
          <div className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity">
            <div onClick={(e) => e.stopPropagation()}>
              <CollectionActions
                collection={collection}
                onDelete={handleDeleteCollection}
                onEdit={handleEditCollection}
              />
            </div>
          </div>
        )}

        {/* Icon and title */}
        <div className="flex items-center gap-3 w-full">
          <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md">
            <BookOpen className="text-muted-foreground h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="font-semibold leading-none">{getCollectionName(collection.name)}</h4>
          </div>
        </div>

        {/* Description - Fixed 3 lines */}
        <p className="text-muted-foreground line-clamp-3 text-sm w-full min-h-[3.75rem]">
          {collection.metadata?.description && typeof collection.metadata.description === "string"
            ? collection.metadata.description
            : "No description"}
        </p>

        {/* Divider */}
        <div className="w-full border-t border-border" />

        {/* Footer with buttons and badges */}
        <div className="flex w-full items-center justify-between gap-3">

          {/* Right side: Info badges */}
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
        </div>
      </Card>
    </>
  );
}

export function CollectionCardLoading() {
  return (
    <Card className="relative flex flex-col items-start gap-3 p-6">
      {/* Icon and title */}
      <div className="flex items-center gap-3 w-full">
        <Skeleton className="h-10 w-10 rounded-md" />
        <Skeleton className="h-5 w-3/4" />
      </div>

      {/* Description */}
      <div className="w-full space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>

      {/* Divider */}
      <div className="w-full border-t border-border" />

      {/* Footer */}
      <div className="flex w-full items-center justify-between gap-3">
        <Skeleton className="h-8 w-40" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-6" />
          <Skeleton className="h-6 w-12" />
        </div>
      </div>
    </Card>
  );
} 