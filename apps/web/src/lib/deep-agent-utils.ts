 

/**
 * Check if an assistant schema indicates it's a deep agent
 * by looking for todos and files in the state schema
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

  // Check if the schema has properties for todos and files
  const properties = parsedSchema.properties || {};
  
  
  const hasTodos = "todos" in properties;
  const hasFiles = "files" in properties;
  
  
  
  return hasTodos && hasFiles;
}

/**
 * Extract todos and files from a deep agent state update
 */
export function extractDeepAgentWorkspaceData(
  stateUpdate: Record<string, any>
): { todos: any[]; files: Record<string, string> } {
  
  
  const todos = [];
  const files: Record<string, string> = {};

  // Prefer top-level keys first (common shape: { messages, todos, files })
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

  // Also scan nested nodes for robustness
  Object.values(stateUpdate).forEach((nodeData: any) => {
    // Node with embedded todos/files
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
    }
  });

  
  return { todos, files };
}

/**
 * Check if a state update contains deep agent workspace data
 */
export function hasDeepAgentWorkspaceData(stateUpdate: Record<string, any>): boolean {
  

  // Top-level fast path
  const topLevelTodos = Array.isArray((stateUpdate as any).todos) && (stateUpdate as any).todos.length > 0;
  const topLevelFiles = (stateUpdate as any).files && typeof (stateUpdate as any).files === "object" && Object.keys((stateUpdate as any).files).length > 0;

  if (topLevelTodos || topLevelFiles) {
    
    return true;
  }

  // Nested scan
  const hasData = Object.values(stateUpdate).some((nodeData: any) => {
    if (!nodeData || typeof nodeData !== "object") return false;
    const hasTodos = Array.isArray((nodeData as any).todos) && (nodeData as any).todos.length > 0;
    const hasFiles = (nodeData as any).files && typeof (nodeData as any).files === "object" && Object.keys((nodeData as any).files).length > 0;
    return hasTodos || hasFiles;
  });
  
  
  return hasData;
}
