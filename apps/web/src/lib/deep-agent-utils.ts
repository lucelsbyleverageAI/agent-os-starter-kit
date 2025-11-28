 

import { PublishedFile } from "@/types/deep-agent";

/**
 * Check if an assistant schema indicates it's a deep agent
 * by looking for todos, files, or published_files in the state schema
 */
export function isDeepAgentSchema(stateSchema: any): boolean {


  if (!stateSchema) {

    return false;
  }

  // Parse if it's a string
  let parsedSchema = stateSchema;
  if (typeof stateSchema === 'string') {
    try {
      parsedSchema = JSON.parse(stateSchema);

    } catch (error) {
      console.error('❌ Failed to parse state schema string:', error);
      return false;
    }
  }

  if (typeof parsedSchema !== "object") {

    return false;
  }

  // Check if the schema has properties for todos and files (or published_files for skills_deepagent)
  const properties = parsedSchema.properties || {};


  const hasTodos = "todos" in properties;
  const hasFiles = "files" in properties;
  const hasPublishedFiles = "published_files" in properties;



  // Support both legacy deepagent (todos + files) and skills_deepagent (todos + published_files)
  return hasTodos && (hasFiles || hasPublishedFiles);
}

/**
 * Extract todos, files, and published_files from a deep agent state update
 */
export function extractDeepAgentWorkspaceData(
  stateUpdate: Record<string, any>
): { todos: any[]; files: Record<string, string>; publishedFiles: PublishedFile[] } {


  const todos: any[] = [];
  const files: Record<string, string> = {};
  let publishedFiles: PublishedFile[] = [];

  // Prefer top-level keys first (common shape: { messages, todos, files, published_files })
  if (Array.isArray((stateUpdate as any).todos)) {
    todos.push(...(stateUpdate as any).todos);
  }
  if ((stateUpdate as any).files && typeof (stateUpdate as any).files === "object") {
    Object.entries((stateUpdate as any).files).forEach(([path, fileEntry]: [string, any]) => {
      if (fileEntry && typeof fileEntry === "object" && fileEntry.content) {
        files[path] = fileEntry.content;
      } else if (typeof fileEntry === "string") {
        files[path] = fileEntry;
      }
    });
  }
  // Extract published_files (from skills_deepagent)
  if (Array.isArray((stateUpdate as any).published_files)) {
    publishedFiles = (stateUpdate as any).published_files;
  }

  // Also scan nested nodes for robustness
  Object.values(stateUpdate).forEach((nodeData: any) => {
    // Node with embedded todos/files/published_files
    if (nodeData && typeof nodeData === "object") {
      if (Array.isArray(nodeData.todos)) {
        todos.push(...nodeData.todos);
      }
      if (nodeData.files && typeof nodeData.files === "object") {
        Object.entries(nodeData.files).forEach(([path, fileEntry]: [string, any]) => {
          if (fileEntry && typeof fileEntry === "object" && fileEntry.content) {
            files[path] = fileEntry.content;
          } else if (typeof fileEntry === "string") {
            files[path] = fileEntry;
          }
        });
      }
      // Also check nested published_files
      if (Array.isArray(nodeData.published_files) && publishedFiles.length === 0) {
        publishedFiles = nodeData.published_files;
      }
    }
  });


  return { todos, files, publishedFiles };
}

/**
 * Check if a state update contains deep agent workspace data
 */
export function hasDeepAgentWorkspaceData(stateUpdate: Record<string, any>): boolean {


  // Top-level fast path
  const topLevelTodos = Array.isArray((stateUpdate as any).todos) && (stateUpdate as any).todos.length > 0;
  const topLevelFiles = (stateUpdate as any).files && typeof (stateUpdate as any).files === "object" && Object.keys((stateUpdate as any).files).length > 0;
  const topLevelPublishedFiles = Array.isArray((stateUpdate as any).published_files) && (stateUpdate as any).published_files.length > 0;

  if (topLevelTodos || topLevelFiles || topLevelPublishedFiles) {

    return true;
  }

  // Nested scan
  const hasData = Object.values(stateUpdate).some((nodeData: any) => {
    if (!nodeData || typeof nodeData !== "object") return false;
    const hasTodos = Array.isArray((nodeData as any).todos) && (nodeData as any).todos.length > 0;
    const hasFiles = (nodeData as any).files && typeof (nodeData as any).files === "object" && Object.keys((nodeData as any).files).length > 0;
    const hasPublishedFiles = Array.isArray((nodeData as any).published_files) && (nodeData as any).published_files.length > 0;
    return hasTodos || hasFiles || hasPublishedFiles;
  });


  return hasData;
}
