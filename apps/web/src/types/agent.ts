import { Assistant, GraphSchema } from "@langchain/langgraph-sdk";

/**
 * Complete schema response from /schemas endpoint
 * Uses LangGraph SDK types for consistency
 */
export interface AgentSchemaResponse {
  graph_id: string;
  input_schema: GraphSchema["input_schema"];
  output_schema: GraphSchema["output_schema"];
  state_schema: GraphSchema["state_schema"];
  config_schema: GraphSchema["config_schema"];
}

/**
 * Input mode for dynamic input composer
 */
export type InputMode = 'chat' | 'form' | 'loading';

export interface Agent extends Assistant {
  deploymentId: string;
  supportedConfigs?: ["tools" | "rag" | "supervisor"];
  
  // Permission metadata
  permission_level?: "owner" | "editor" | "viewer" | "admin";
  owner_id?: string;
  owner_display_name?: string;
  shared_users_count?: number;
  
  // Graph metadata for discovery
  type?: "graph" | "assistant";
  needs_initialization?: boolean;
  schema_accessible?: boolean;
  
  // Schema warming state
  schemas_warming?: boolean;
}

/**
 * Response from the permission-aware discovery endpoint
 */
export interface DiscoveryResponse {
  // Permission-filtered graphs available to user
  valid_graphs: GraphInfo[];
  invalid_graphs: GraphInfo[];
  
  // Permission-filtered assistants accessible to user
  assistants: AssistantInfo[];
  
  // User context for role-based UI
  user_role: 'dev_admin' | 'business_admin' | 'user';
  is_dev_admin: boolean;
  
  // Metadata
  scan_metadata: {
    langgraph_graphs_found: number;
    valid_graphs: number;
    invalid_graphs: number;
    scan_duration_ms: number;
  };
  assistant_counts: {
    total: number;
    owned: number;
    shared: number;
  };
  
  // Deployment context
  deployment_id: string;
  deployment_name: string;
}

/**
 * Graph information from discovery scan
 */
export interface GraphInfo {
  graph_id: string;
  schema_accessible: boolean;
  assistants_count: number;
  has_default_assistant: boolean;
  needs_initialization: boolean;
  error?: string;
  cleanup_required?: boolean;
  
  // Permission context
  user_permission_level?: "admin" | "access";
  created_at?: string;
  // Presentation
  name?: string;
  description?: string | null;
}

/**
 * Assistant information with permission metadata
 */
export interface AssistantInfo {
  assistant_id: string;
  graph_id: string;
  name: string;
  description?: string | null;
  permission_level: "owner" | "editor" | "viewer" | "admin";
  owner_id: string;
  owner_display_name?: string;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

/**
 * Combined agent data for UI display
 */
export interface AgentDisplayItem {
  id: string;
  type: "graph" | "assistant";
  name: string;
  description?: string;
  graph_id: string;
  permission_level?: "owner" | "editor" | "viewer" | "admin";
  owner_display_name?: string;
  needs_initialization?: boolean;
  schema_accessible?: boolean;
  assistants_count?: number;
  metadata?: Record<string, any>;
  
  // Assistant-specific fields
  assistant_id?: string;
  owner_id?: string;
  created_at?: string;
  updated_at?: string;
  supportedConfigs?: ["tools" | "rag" | "supervisor"];
}
