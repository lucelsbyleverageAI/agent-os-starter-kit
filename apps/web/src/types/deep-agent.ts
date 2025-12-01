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

// Published file from skills_deepagent - stored in cloud storage
export interface PublishedFile {
  display_name: string;
  description: string;
  filename: string;
  file_type: string;
  mime_type: string;
  file_size: number;
  storage_path: string;
  sandbox_path: string;
  published_at: string;
}

export interface DeepAgentState {
  todos?: TodoItem[];
  files?: Record<string, FileEntry>;
  published_files?: PublishedFile[];
  messages?: any[];
  remaining_steps?: number;
}

export interface DeepAgentWorkspaceData {
  todos: TodoItem[];
  files: Record<string, string>; // Legacy: path -> content mapping
  publishedFiles: PublishedFile[]; // New: cloud-stored files from skills_deepagent
}
