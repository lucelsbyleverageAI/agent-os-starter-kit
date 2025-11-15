"use client";

import type React from "react";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { 
  Trash2, 
  MoreVertical, 
  Calendar, 
  Eye, 
  X, 
  Search,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Brain,
  Edit,
  Hash
} from "lucide-react";
import { Memory } from "@/types/memory";
import { useMemoriesContext } from "../providers/Memories";
import { format } from "date-fns";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { EditMemoryDialog } from "./edit-memory-dialog";
import { ViewPayloadDialog } from "./view-payload-dialog";

// Truncate memory content helper
const truncateContent = (content: string, maxLength: number = 60): { truncated: string; isTruncated: boolean } => {
  if (content.length <= maxLength) {
    return { truncated: content, isTruncated: false };
  }
  return { truncated: `${content.substring(0, maxLength)}...`, isTruncated: true };
};

// Sort configuration
type SortField = 'content' | 'created' | 'updated';
type SortDirection = 'asc' | 'desc';

interface SortConfig {
  field: SortField;
  direction: SortDirection;
}

// Fuzzy search helper
const fuzzyMatch = (searchTerm: string, text: string): boolean => {
  if (!searchTerm) return true;
  
  const search = searchTerm.toLowerCase();
  const target = text.toLowerCase();
  
  // Simple fuzzy matching: check if all characters of search term appear in order
  let searchIndex = 0;
  for (let i = 0; i < target.length && searchIndex < search.length; i++) {
    if (target[i] === search[searchIndex]) {
      searchIndex++;
    }
  }
  
  return searchIndex === search.length || target.includes(search);
};

interface MemoriesTableProps {
  memories: Memory[];
  loading?: boolean;
  onMemoryDeleted?: () => void | Promise<void>;
  onMemoriesChanged?: () => void | Promise<void>;
}

export function MemoriesTable({
  memories,
  loading = false,
  onMemoryDeleted,
  onMemoriesChanged,
}: MemoriesTableProps) {
  const { deleteMemory } = useMemoriesContext();
  const [deletingMemoryId, setDeletingMemoryId] = useState<string | null>(null);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [viewingMemory, setViewingMemory] = useState<Memory | null>(null);
  
  // Multi-select state
  const [selectedMemories, setSelectedMemories] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [showBatchDeleteDialog, setShowBatchDeleteDialog] = useState(false);
  
  // Search and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState<SortConfig>({ field: 'created', direction: 'desc' });
  
  // Refs for table
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // Filtered and sorted memories
  const processedMemories = useMemo(() => {
    let filtered = memories;
    
    // Apply search filter
    if (searchTerm.trim()) {
      filtered = memories.filter(memory => 
        fuzzyMatch(searchTerm, memory.memory)
      );
    }
    
    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let comparison = 0;
      
      if (sortConfig.field === 'content') {
        comparison = a.memory.localeCompare(b.memory);
      } else if (sortConfig.field === 'created') {
        const dateA = new Date(a.created_at).getTime();
        const dateB = new Date(b.created_at).getTime();
        comparison = dateA - dateB;
      } else if (sortConfig.field === 'updated') {
        const dateA = new Date(a.updated_at || a.created_at).getTime();
        const dateB = new Date(b.updated_at || b.created_at).getTime();
        comparison = dateA - dateB;
      }
      
      return sortConfig.direction === 'asc' ? comparison : -comparison;
    });
    
    return sorted;
  }, [memories, searchTerm, sortConfig]);

  // Handle sorting
  const handleSort = useCallback((field: SortField) => {
    setSortConfig(prev => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  }, []);

  // Get sort icon for column header
  const getSortIcon = useCallback((field: SortField) => {
    if (sortConfig.field !== field) {
      return <ChevronsUpDown className="h-3 w-3 ml-1 text-muted-foreground/50" />;
    }
    
    return sortConfig.direction === 'asc' 
      ? <ChevronUp className="h-3 w-3 ml-1 text-foreground" />
      : <ChevronDown className="h-3 w-3 ml-1 text-foreground" />;
  }, [sortConfig]);

  // Multi-select handlers
  const isAllVisibleSelected = processedMemories.length > 0 && processedMemories.every(memory => selectedMemories.has(memory.id));
  const isIndeterminate = selectedMemories.size > 0 && !isAllVisibleSelected;

  const handleSelectAll = useCallback((checked: boolean) => {
    if (checked) {
      const newSelected = new Set(selectedMemories);
      processedMemories.forEach(memory => newSelected.add(memory.id));
      setSelectedMemories(newSelected);
    } else {
      const newSelected = new Set(selectedMemories);
      processedMemories.forEach(memory => newSelected.delete(memory.id));
      setSelectedMemories(newSelected);
    }
  }, [processedMemories, selectedMemories]);

  const handleSelectMemory = useCallback((memoryId: string, checked: boolean) => {
    const newSelected = new Set(selectedMemories);
    if (checked) {
      newSelected.add(memoryId);
    } else {
      newSelected.delete(memoryId);
    }
    setSelectedMemories(newSelected);
  }, [selectedMemories]);

  const clearSelection = useCallback(() => {
    setSelectedMemories(new Set());
  }, []);

  // Get selected memory details for batch operations
  const selectedMemoryDetails = processedMemories.filter(memory => selectedMemories.has(memory.id));

  // Handle batch delete
  const handleBatchDelete = useCallback(async () => {
    if (selectedMemories.size === 0) return;

    setBatchDeleting(true);
    setShowBatchDeleteDialog(false);

    const memoriesToDelete = Array.from(selectedMemories);
    const totalCount = memoriesToDelete.length;
    let successCount = 0;
    let failureCount = 0;

    const loadingToast = toast.loading(`Deleting ${totalCount} memories...`, {
      richColors: true,
    });

    try {
      // Delete memories one by one (silent mode to avoid individual toasts)
      for (const memoryId of memoriesToDelete) {
        try {
          const success = await deleteMemory(memoryId, true);
          if (success) {
            successCount++;
          } else {
            failureCount++;
          }
        } catch (_error) {
          console.error(`Failed to delete memory ${memoryId}:`, _error);
          failureCount++;
        }
      }

      toast.dismiss(loadingToast);

      if (failureCount === 0) {
        toast.success(`Successfully deleted ${successCount} memories`, {
          richColors: true,
        });
      } else {
        toast.warning(`Deleted ${successCount} memories, ${failureCount} failed`, {
          richColors: true,
          description: "Some memories could not be deleted. Please try again."
        });
      }

      // Clear selection and refresh
      clearSelection();
      if (onMemoryDeleted) {
        await onMemoryDeleted();
      }

    } catch (_error) {
      toast.dismiss(loadingToast);
      toast.error("Batch delete failed", {
        richColors: true,
        description: "An unexpected error occurred during batch deletion."
      });
    } finally {
      setBatchDeleting(false);
    }
  }, [selectedMemories, deleteMemory, clearSelection, onMemoryDeleted]);

  // Handle memory deletion
  const handleDeleteMemory = async (memoryId: string, memoryContent: string) => {
    const memoryExists = memories.some(memory => memory.id === memoryId);
    if (!memoryExists) {
      toast.error("Memory not found", {
        richColors: true,
        description: "The memory may have already been deleted."
      });
      return;
    }

    const loadingToast = toast.loading("Deleting memory", {
      richColors: true,
      description: `Removing memory...`
    });
    
    setDeletingMemoryId(memoryId);
    
    try {
      const success = await deleteMemory(memoryId);
      
      toast.dismiss(loadingToast);
      
      if (success) {
        // Remove from selection if it was selected
        if (selectedMemories.has(memoryId)) {
          const newSelected = new Set(selectedMemories);
          newSelected.delete(memoryId);
          setSelectedMemories(newSelected);
        }
        
        // Call the callback to refresh the parent's memory list
        if (onMemoryDeleted) {
          await onMemoryDeleted();
        }
      }
      
    } catch (error) {
      toast.dismiss(loadingToast);
      console.error("❌ Delete memory error:", error);
    } finally {
      setDeletingMemoryId(null);
    }
  };

  // Clear selection when memories change (e.g., after refresh)
  useEffect(() => {
    setSelectedMemories(prev => {
      const currentMemoryIds = new Set(memories.map(memory => memory.id));
      const filteredSelection = new Set(Array.from(prev).filter(id => currentMemoryIds.has(id)));
      return filteredSelection;
    });
  }, [memories]);

  // Clear search when no memories match
  const clearSearch = useCallback(() => {
    setSearchTerm('');
  }, []);

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search memories..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9 pr-9 focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          {searchTerm && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearSearch}
              className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0 hover:bg-muted"
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
        
        {/* Memory Count Badge */}
        <div className="flex items-center">
          <MinimalistBadgeWithText
            icon={Brain}
            text={searchTerm ? 
              `${processedMemories.length} of ${memories.length}` : 
              `${memories.length}`
            }
            tooltip={searchTerm ? 
              `Showing ${processedMemories.length} memories matching "${searchTerm}" out of ${memories.length} total` :
              `${memories.length} memories stored`
            }
          />
        </div>
      </div>

      <div className="rounded-xl border border-border overflow-hidden">
        {/* Bulk Actions Bar */}
        {selectedMemories.size > 0 && (
          <div className="bg-primary/10 border-b border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">
                  {selectedMemories.size} memory{selectedMemories.size === 1 ? '' : 'ies'} selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearSelection}
                  className="h-7 px-2 text-xs"
                >
                  <X className="h-3 w-3 mr-1" />
                  Clear
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setShowBatchDeleteDialog(true)}
                  disabled={batchDeleting}
                  className="h-7 px-3 text-xs"
                >
                  <Trash2 className="h-3 w-3 mr-1" />
                  {batchDeleting ? "Deleting..." : "Delete Selected"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Frozen Header */}
        <div className="bg-muted/30 border-b border-border">
          <div className="grid grid-cols-12 gap-4 px-4 py-3">
            <div className="col-span-1 flex items-center">
              <Checkbox
                checked={isAllVisibleSelected}
                onCheckedChange={handleSelectAll}
                disabled={processedMemories.length === 0 || loading}
                className="data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground"
                {...(isIndeterminate && { 'data-state': 'indeterminate' })}
              />
            </div>
            <div className="col-span-5 flex items-center">
              <button
                onClick={() => handleSort('content')}
                className="flex items-center text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Memory Content
                {getSortIcon('content')}
              </button>
            </div>
            <div className="col-span-2 flex items-center">
              <button
                onClick={() => handleSort('created')}
                className="flex items-center text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Created
                {getSortIcon('created')}
              </button>
            </div>
            <div className="col-span-2 flex items-center">
              <button
                onClick={() => handleSort('updated')}
                className="flex items-center text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Updated
                {getSortIcon('updated')}
              </button>
            </div>
            <div className="col-span-2 text-xs font-medium text-muted-foreground text-right">
              Actions
            </div>
          </div>
        </div>

        {/* Scrollable Content */}
        <div 
          ref={tableContainerRef}
          className={cn(
            "max-h-[60vh] overflow-y-auto",
            ...getScrollbarClasses('y')
          )}
        >
          {processedMemories.length === 0 && !loading ? (
            <div className="text-sm text-muted-foreground text-center py-8 px-4">
              {searchTerm ? (
                <div className="space-y-2">
                  <div>No memories found matching "{searchTerm}"</div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearSearch}
                    className="text-xs"
                  >
                    Clear search
                  </Button>
                </div>
              ) : (
                "No memories found. Create your first memory to get started."
              )}
            </div>
          ) : (
            <>
              {processedMemories.map((memory, index) => {
                const { truncated: displayContent, isTruncated } = truncateContent(memory.memory);
                const isLastRow = index === processedMemories.length - 1;
                const isSelected = selectedMemories.has(memory.id);
                
                return (
                  <div 
                    key={memory.id}
                    className={cn(
                      "grid grid-cols-12 gap-4 px-4 py-3 hover:bg-accent/50 transition-colors",
                      !isLastRow && "border-b border-border/30",
                      deletingMemoryId === memory.id && "opacity-50 pointer-events-none",
                      isSelected && "bg-primary/5"
                    )}
                  >
                    {/* Checkbox */}
                    <div className="col-span-1 flex items-center">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={(checked: boolean) => handleSelectMemory(memory.id, checked)}
                        disabled={deletingMemoryId === memory.id || batchDeleting}
                      />
                    </div>

                    {/* Memory Content */}
                    <div className="col-span-5 flex items-center">
                      {isTruncated ? (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="text-sm font-normal truncate cursor-help">
                                {displayContent}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs break-words text-sm">
                                {memory.memory}
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ) : (
                        <span className="text-sm font-normal truncate">
                          {displayContent}
                        </span>
                      )}
                    </div>

                    {/* Created Date */}
                    <div className="col-span-2 flex items-center">
                      <MinimalistBadgeWithText
                        icon={Calendar}
                        text={format(new Date(memory.created_at), "MMM d, yyyy")}
                        tooltip={format(new Date(memory.created_at), "MMMM d, yyyy 'at' h:mm a")}
                      />
                    </div>

                    {/* Updated Date */}
                    <div className="col-span-2 flex items-center">
                      <MinimalistBadgeWithText
                        icon={Calendar}
                        text={memory.updated_at ? 
                          format(new Date(memory.updated_at), "MMM d, yyyy") : 
                          "Never"
                        }
                        tooltip={memory.updated_at ? 
                          format(new Date(memory.updated_at), "MMMM d, yyyy 'at' h:mm a") :
                          "Memory has not been updated"
                        }
                      />
                    </div>

                    {/* Actions */}
                    <div className="col-span-2 flex items-center justify-end">
                      <AlertDialog>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-foreground"
                              disabled={deletingMemoryId === memory.id || batchDeleting}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setEditingMemory(memory)}
                              disabled={deletingMemoryId === memory.id || batchDeleting}
                            >
                              <Edit className="mr-2 h-4 w-4" />
                              Edit Memory
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => setViewingMemory(memory)}
                              disabled={deletingMemoryId === memory.id || batchDeleting}
                            >
                              <Eye className="mr-2 h-4 w-4" />
                              View Full Payload
                            </DropdownMenuItem>
                            <AlertDialogTrigger asChild>
                              <DropdownMenuItem
                                className="text-destructive"
                                disabled={deletingMemoryId === memory.id || batchDeleting}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                {deletingMemoryId === memory.id ? "Deleting..." : "Delete"}
                              </DropdownMenuItem>
                            </AlertDialogTrigger>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle className="text-lg font-medium">
                              Delete Memory
                            </AlertDialogTitle>
                            <AlertDialogDescription asChild>
                              <div className="text-sm text-muted-foreground">
                                Are you sure you want to delete this memory?
                                <div className="mt-2 p-2 bg-muted rounded text-xs">
                                  "{truncateContent(memory.memory, 100).truncated}"
                                </div>
                                This action cannot be undone and will permanently remove the memory.
                              </div>
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel 
                              className="text-sm"
                              disabled={deletingMemoryId === memory.id}
                            >
                              Cancel
                            </AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => 
                                await handleDeleteMemory(memory.id, memory.memory)
                              }
                              className="bg-destructive hover:bg-destructive/90 text-white text-sm"
                              disabled={deletingMemoryId === memory.id}
                            >
                              {deletingMemoryId === memory.id ? "Deleting..." : "Delete Memory"}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                );
              })}

              {/* Initial Loading State */}
              {loading && processedMemories.length === 0 && (
                <div className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Hash className="h-4 w-4 animate-pulse" />
                    Loading memories...
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Batch Delete Confirmation Dialog */}
        <AlertDialog open={showBatchDeleteDialog} onOpenChange={setShowBatchDeleteDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="text-lg font-medium">
                Delete {selectedMemories.size} Memories
              </AlertDialogTitle>
              <AlertDialogDescription asChild>
                <div className="text-sm text-muted-foreground">
                  Are you sure you want to delete {selectedMemories.size} selected memory{selectedMemories.size === 1 ? '' : 'ies'}?
                  {selectedMemoryDetails.length > 0 && (
                    <div className="mt-3 p-3 bg-muted rounded-md">
                      <div className="text-xs font-medium text-foreground mb-2">Memories to be deleted:</div>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {selectedMemoryDetails.slice(0, 5).map(memory => (
                          <div key={memory.id} className="text-xs text-muted-foreground">
                            • {truncateContent(memory.memory, 50).truncated}
                          </div>
                        ))}
                        {selectedMemoryDetails.length > 5 && (
                          <div className="text-xs text-muted-foreground font-medium">
                            ... and {selectedMemoryDetails.length - 5} more
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  <div className="mt-3 text-sm font-medium text-destructive">
                    This action cannot be undone and will permanently remove these memories.
                  </div>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={batchDeleting}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleBatchDelete}
                className="bg-destructive hover:bg-destructive/90 text-white"
                disabled={batchDeleting}
              >
                {batchDeleting ? "Deleting..." : `Delete ${selectedMemories.size} Memories`}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Edit Memory Dialog */}
        <EditMemoryDialog
          memory={editingMemory}
          open={!!editingMemory}
          onOpenChange={(open: boolean) => !open && setEditingMemory(null)}
        />

        {/* View Payload Dialog */}
        <ViewPayloadDialog
          memory={viewingMemory}
          open={!!viewingMemory}
          onOpenChange={(open: boolean) => !open && setViewingMemory(null)}
        />
      </div>
    </div>
  );
}
