"use client";

import React, { useMemo, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Circle,
  Clock,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { TodoItem, FileItem, PublishedFile } from "@/types/deep-agent";
import { useFilePreviewOptional } from "@/features/chat/context/file-preview-context";
import { BrandedFileIcon } from "@/components/ui/branded-file-icon";

interface TasksFilesSidebarProps {
  todos: TodoItem[];
  files: Record<string, string>;
  publishedFiles: PublishedFile[];
  onFileClick: (file: FileItem) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export const TasksFilesSidebar = React.memo<TasksFilesSidebarProps>(
  ({ todos, files, publishedFiles, onFileClick, collapsed, onToggleCollapse }) => {
    const filePreview = useFilePreviewOptional();

    const getStatusIcon = useCallback((status: TodoItem["status"]) => {
      switch (status) {
        case "completed":
          return <CheckCircle size={16} className="text-green-500" />;
        case "in_progress":
          return <Clock size={16} className="text-yellow-500" />;
        default:
          return <Circle size={16} className="text-muted-foreground" />;
      }
    }, []);

    const groupedTodos = useMemo(() => {
      return {
        pending: todos.filter((t) => t.status === "pending"),
        in_progress: todos.filter((t) => t.status === "in_progress"),
        completed: todos.filter((t) => t.status === "completed"),
      };
    }, [todos]);

    // Handler for published file clicks - opens preview panel
    const handlePublishedFileClick = useCallback((file: PublishedFile) => {
      if (filePreview) {
        filePreview.openPreview({
          display_name: file.display_name,
          filename: file.filename,
          file_type: file.file_type,
          mime_type: file.mime_type,
          storage_path: file.storage_path,
          file_size: file.file_size,
          description: file.description,
        });
      }
    }, [filePreview]);

    // Calculate total files count for tab
    const totalFilesCount = Object.keys(files).length + publishedFiles.length;

    if (collapsed) {
      return (
        <div
          className="w-12 h-full bg-card border-r flex items-center justify-center flex-shrink-0 cursor-pointer"
          role="button"
          aria-label="Expand workspace sidebar"
          tabIndex={0}
          onClick={onToggleCollapse}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onToggleCollapse();
            }
          }}
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onToggleCollapse();
            }}
            className="p-2"
          >
            <ChevronRight size={20} />
          </Button>
        </div>
      );
    }

    return (
      <div className="w-80 h-full bg-card border-r flex flex-col flex-shrink-0 overflow-hidden">
        <div className="flex justify-between items-center p-4 h-16 border-b">
          <h2 className="text-lg font-semibold">Workspace</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleCollapse}
            className="p-2"
          >
            <ChevronLeft size={20} />
          </Button>
        </div>
        
        <Tabs defaultValue="tasks" className="flex flex-col flex-1 overflow-hidden">
          <TabsList variant="branded" className="mx-4 mt-4">
            <TabsTrigger value="tasks">
              Tasks ({todos.length})
            </TabsTrigger>
            <TabsTrigger value="files">
              Files ({totalFilesCount})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="tasks" className="flex-1 p-0 overflow-hidden">
            <ScrollArea className="h-full">
              {todos.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  <p className="text-sm">No tasks yet</p>
                </div>
              ) : (
                <div className="p-4 space-y-6">
                  {groupedTodos.in_progress.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        In Progress
                      </h3>
                      {groupedTodos.in_progress.map((todo, index) => (
                        <div
                          key={`in_progress_${index}`}
                          className="flex items-start gap-3 p-2 rounded-md"
                        >
                          {getStatusIcon(todo.status)}
                          <span className="text-sm leading-normal flex-1">
                            {todo.content}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {groupedTodos.pending.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        Pending
                      </h3>
                      {groupedTodos.pending.map((todo, index) => (
                        <div
                          key={`pending_${index}`}
                          className="flex items-start gap-3 p-2 rounded-md"
                        >
                          {getStatusIcon(todo.status)}
                          <span className="text-sm leading-normal flex-1">
                            {todo.content}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {groupedTodos.completed.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        Completed
                      </h3>
                      {groupedTodos.completed.map((todo, index) => (
                        <div
                          key={`completed_${index}`}
                          className="flex items-start gap-3 p-2 rounded-md"
                        >
                          {getStatusIcon(todo.status)}
                          <span className="text-sm leading-normal flex-1 opacity-75">
                            {todo.content}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          <TabsContent value="files" className="flex-1 p-0 overflow-hidden">
            <ScrollArea className="h-full">
              {totalFilesCount === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  <p className="text-sm">No files yet</p>
                </div>
              ) : (
                <div className="p-4 space-y-4">
                  {/* Published Files Section (prioritized - show first) */}
                  {publishedFiles.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        Published Files
                      </h3>
                      {publishedFiles.map((file) => (
                          <div
                            key={file.storage_path}
                            className="flex items-center gap-3 p-2 rounded-md cursor-pointer hover:bg-muted/50 transition-colors"
                            onClick={() => handlePublishedFileClick(file)}
                          >
                            <BrandedFileIcon extension={file.file_type} size={20} className="flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <span className="text-sm font-medium leading-normal truncate block">
                                {file.display_name}
                              </span>
                              {file.description && (
                                <span className="text-xs text-muted-foreground leading-normal truncate block">
                                  {file.description}
                                </span>
                              )}
                            </div>
                          </div>
                      ))}
                    </div>
                  )}

                  {/* Legacy Working Files Section */}
                  {Object.keys(files).length > 0 && (
                    <div className="space-y-2">
                      {publishedFiles.length > 0 && (
                        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                          Working Files
                        </h3>
                      )}
                      {Object.keys(files).map((filePath) => {
                        const fileExt = filePath.split('.').pop() || '';
                        return (
                        <div key={filePath} className="group">
                          <div
                            className="flex items-center gap-3 p-2 rounded-md cursor-pointer hover:bg-muted/50 transition-colors"
                            onClick={() =>
                              onFileClick({ path: filePath, content: files[filePath] })
                            }
                            style={{ maxWidth: 'calc(20rem - 2rem)' }}
                          >
                            <BrandedFileIcon extension={fileExt} size={16} className="flex-shrink-0" />
                            <div className="flex-1 min-w-0" style={{ maxWidth: 'calc(100% - 28px)' }}>
                              <p
                                className="text-sm leading-tight break-all"
                                title={filePath}
                              >
                                {filePath}
                              </p>
                            </div>
                          </div>
                        </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    );
  },
);

TasksFilesSidebar.displayName = "TasksFilesSidebar";
