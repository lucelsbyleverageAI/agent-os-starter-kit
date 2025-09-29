"use client";

import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Card, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import type { Collection } from "@/types/collection";
import {
  DEFAULT_COLLECTION_NAME,
  getCollectionName,
} from "../../hooks/use-knowledge";
import { cn } from "@/lib/utils";
import { CollectionActions } from "./collection-actions";
import { Crown, Edit, Eye } from "lucide-react";

interface CollectionsListProps {
  collections: Collection[];
  selectedCollection: Collection | undefined;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onEdit: (
    id: string,
    name: string,
    metadata: Record<string, any>,
  ) => Promise<void>;
  currentPage: number;
  itemsPerPage: number;
  totalCollections: number;
  onPageChange: (page: number) => void;
}

// Helper function to get permission icon and tooltip
function getPermissionIconAndTooltip(permissionLevel?: string) {
  switch (permissionLevel) {
    case 'owner':
      return { 
        icon: Crown, 
        tooltip: 'Owner - You own this collection and can edit, delete, share with others, and manage all user permissions'
      };
    case 'editor':
      return { 
        icon: Edit, 
        tooltip: 'Editor - You can edit this collection but cannot delete it or manage sharing permissions' 
      };
    case 'viewer':
      return { 
        icon: Eye, 
        tooltip: 'Viewer - You can view this collection but cannot edit, delete, or manage permissions' 
      };
    default:
      return { 
        icon: Crown, 
        tooltip: 'Owner - You own this collection and can edit, delete, share with others, and manage all user permissions'
      };
  }
}

export function CollectionsList({
  collections,
  selectedCollection,
  onSelect,
  onDelete,
  onEdit,
  currentPage,
  itemsPerPage,
  totalCollections,
  onPageChange,
}: CollectionsListProps) {
  const totalPages = Math.ceil(totalCollections / itemsPerPage);

  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedCollections = collections.slice(startIndex, endIndex);

  return (
    <div>
      <div className="grid gap-4">
        {paginatedCollections.map((collection) => {
          const permissionDisplay = getPermissionIconAndTooltip(collection.permission_level);
          const isSelected = selectedCollection?.uuid === collection.uuid;
          
          return (
            <Card
              key={collection.uuid}
              className={cn(
                "overflow-hidden relative group h-44 flex flex-col transition-all duration-300 ease-out cursor-pointer vibrate-on-hover",
                isSelected 
                  ? "border-primary border-2 shadow-lg shadow-primary/10" 
                  : "hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10"
              )}
              onClick={() => onSelect(collection.uuid)}
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
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                      <CollectionActions
                        collection={collection}
                        onDelete={onDelete}
                        onEdit={onEdit}
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
                {/* Left side: Permission badge */}
                <div className="flex items-center gap-2">
                  <MinimalistBadge
                    icon={permissionDisplay.icon}
                    tooltip={permissionDisplay.tooltip}
                  />
                </div>

                {/* Right side: Could add action icons here if needed */}
                <div className="flex items-center gap-1">
                  {/* Future: Add quick action buttons here */}
                </div>
              </CardFooter>
            </Card>
          );
        })}
      </div>

      {totalPages > 1 && (
        <Pagination className="mt-4">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onPageChange(Math.max(1, currentPage - 1));
                }}
                aria-disabled={currentPage === 1}
                className={cn(
                  currentPage === 1
                    ? "text-muted-foreground pointer-events-none"
                    : undefined,
                )}
              />
            </PaginationItem>
            {[...Array(totalPages)].map((_, page) => (
              <PaginationItem key={page + 1}>
                <PaginationLink
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    onPageChange(page + 1);
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
                  onPageChange(Math.min(totalPages, currentPage + 1));
                }}
                aria-disabled={currentPage === totalPages}
                className={cn(
                  currentPage === totalPages
                    ? "text-muted-foreground pointer-events-none"
                    : undefined,
                )}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </div>
  );
}
