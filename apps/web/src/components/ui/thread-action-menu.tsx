"use client";

import { MoreHorizontal, Trash2, Edit3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ThreadActionMenuProps {
  onDelete: () => void;
  onRename: () => void;
  disabled?: boolean;
  useNamedGroup?: boolean;
}

export function ThreadActionMenu({ onDelete, onRename, disabled = false, useNamedGroup = false }: ThreadActionMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={`h-8 w-8 p-0 opacity-0 ${useNamedGroup ? 'group-hover/thread-item:opacity-100' : 'group-hover:opacity-100'} transition-opacity hover:bg-transparent`}
          disabled={disabled}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
          <span className="sr-only">Open menu</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onRename();
          }}
          disabled={disabled}
        >
          <Edit3 className="mr-2 h-4 w-4" />
          Rename thread
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="text-destructive focus:text-destructive"
          disabled={disabled}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Delete thread
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
} 