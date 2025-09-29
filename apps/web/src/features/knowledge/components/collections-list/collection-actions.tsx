import { Collection } from "@/types/collection";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { MoreHorizontal, Users } from "lucide-react";
import { EditCollectionDialog } from "./edit-collection-dialog";
import { DeleteCollectionAlert } from "./delete-collection-alert";
import { ManageSharingDialog } from "./manage-sharing-dialog";
import { useState } from "react";

export function CollectionActions({
  collection,
  onDelete,
  onEdit,
}: {
  collection: Collection;
  onDelete: (id: string) => void;
  onEdit: (
    id: string,
    name: string,
    metadata: Record<string, any>,
  ) => Promise<void>;
}) {
  const [manageSharingOpen, setManageSharingOpen] = useState(false);
  
  // Determine user permissions
  const isOwner = collection.permission_level === 'owner';
  const canEdit = collection.permission_level === 'owner' || collection.permission_level === 'editor';
  
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          asChild
          onClick={(e) => e.stopPropagation()}
        >
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
          >
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">Collection actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {/* Manage Sharing - Only for owners */}
          {isOwner && (
            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation();
                setManageSharingOpen(true);
              }}
            >
              <Users className="mr-2 h-4 w-4" />
              Manage Access
            </DropdownMenuItem>
          )}
          
          {/* Edit Collection - For owners and editors */}
          {canEdit && (
            <EditCollectionDialog
              collection={collection}
              handleEditCollection={onEdit}
            />
          )}
          
          {/* Delete Collection - Only for owners */}
          {isOwner && (
            <>
              {canEdit && <DropdownMenuSeparator />}
              <DeleteCollectionAlert
                collection={collection}
                onDelete={onDelete}
              />
            </>
          )}
          
          {/* If user only has viewer permission, show limited message */}
          {!canEdit && !isOwner && (
            <div className="px-2 py-1 text-xs text-muted-foreground">
              View-only access
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Manage Sharing Dialog */}
      <ManageSharingDialog
        open={manageSharingOpen}
        onOpenChange={setManageSharingOpen}
        collection={collection}
      />
    </>
  );
}
