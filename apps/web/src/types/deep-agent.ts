export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export interface FileEntry {
  content: string;
  metadata?: Record<string, any>;
}

export interface FileItem {
  path: string;
  content: string;
}

export interface DeepAgentState {
  todos?: TodoItem[];
  files?: Record<string, FileEntry>;
  messages?: any[];
  remaining_steps?: number;
}

export interface DeepAgentWorkspaceData {
  todos: TodoItem[];
  files: Record<string, string>; // Simplified to path -> content mapping
}
