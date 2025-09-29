"use client";

import React, { useMemo, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  CheckCircle,
  Circle,
  Clock,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { TodoItem, FileItem } from "@/types/deep-agent";

interface TasksFilesSidebarProps {
  todos: TodoItem[];
  files: Record<string, string>;
  onFileClick: (file: FileItem) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export const TasksFilesSidebar = React.memo<TasksFilesSidebarProps>(
  ({ todos, files, onFileClick, collapsed, onToggleCollapse }) => {
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
          <TabsList className="mx-4 mt-4 grid w-auto grid-cols-2 bg-muted">
            <TabsTrigger value="tasks" className="text-sm">
              Tasks ({todos.length})
            </TabsTrigger>
            <TabsTrigger value="files" className="text-sm">
              Files ({Object.keys(files).length})
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
              {Object.keys(files).length === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  <p className="text-sm">No files yet</p>
                </div>
              ) : (
                <div className="p-4 space-y-1">
                  {Object.keys(files).map((filePath) => (
                    <div key={filePath} className="group">
                      <div
                        className="flex items-center gap-3 p-2 rounded-md cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() =>
                          onFileClick({ path: filePath, content: files[filePath] })
                        }
                        style={{ maxWidth: 'calc(20rem - 2rem)' }}
                      >
                        <FileText size={16} className="text-muted-foreground flex-shrink-0" />
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
                  ))}
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
