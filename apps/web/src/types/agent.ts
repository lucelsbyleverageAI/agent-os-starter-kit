import { Assistant, GraphSchema } from "@langchain/langgraph-sdk";

/**
 * Complete schema response from /schemas endpoint.
 * Uses LangGraph SDK types for consistency with the backend.
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
export type InputMode = 'chat' | 'form' | 'chat-with-config' | 'loading';

/**
 * Agent - Primary type used throughout the frontend for agent instances.
 *
 * This type extends the LangGraph SDK's Assistant type and adds frontend-specific
 * metadata for permissions, UI state, and categorization.
 *
 * **Why this type exists:**
 * - Provides compatibility with LangGraph SDK types (Assistant)
 * - Adds frontend-specific fields (deploymentId, tags, permission_level)
 * - Centralizes agent data structure for UI components
 *
 * **Usage:**
 * - Used by all agent CRUD operations (create, read, update, delete)
 * - Powers agent cards, edit forms, and chat interface
 * - Consumed by utility functions (canUserEditAssistant, etc.)
 *
 * **Data Flow:**
 * 1. Backend API returns AssistantInfo (minimal format)
 * 2. Frontend converts to Agent via convertAssistantInfoToAgent()
 * 3. Agent is stored in AgentsProvider state
 * 4. UI components consume Agent from context
 *
 * **Related Types:**
 * - {@link AssistantInfo} - API response format (gets converted to Agent)
 * - {@link AgentDisplayItem} - Simplified format for admin UI
 *
 * @see {@link https://langchain-ai.github.io/langgraph/cloud/reference/sdk/js_ts_sdk_ref/#assistant | LangGraph Assistant Type}
 */
export interface Agent extends Assistant {
  deploymentId: string;
  supportedConfigs?: ["tools" | "rag" | "supervisor"];

  // Categorization
  tags?: string[];

  // Permission metadata
  permission_level?: "owner" | "editor" | "viewer" | "admin";
  allowed_actions?: string[];  // Backend-provided allowed actions (Phase 4)
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
  allowed_actions?: string[];  // Backend-provided allowed actions (Phase 4)
  created_at?: string;
  // Presentation
  name?: string;
  description?: string | null;
  // Graph template assistant ID for fetching graph template schema
  system_assistant_id?: string;
}

/**
 * AssistantInfo - API response format from LangConnect backend.
 *
 * This is a minimal representation of an assistant returned by the discovery API.
 * It contains only the essential fields needed for list views and permission checks.
 *
 * **Why this type exists:**
 * - Backend API contract - defines what LangConnect returns
 * - Lightweight format for efficient data transfer
 * - Separates API concerns from UI concerns
 *
 * **Usage:**
 * - Returned by `/api/langconnect/user/accessible-graphs` endpoint
 * - Stored in localStorage for caching (AssistantListCache)
 * - Converted to Agent type before use in UI components
 *
 * **Data Flow:**
 * 1. LangConnect API returns AssistantInfo[]
 * 2. AgentsProvider caches AssistantInfo in localStorage
 * 3. AgentsProvider converts to Agent[] via convertAssistantInfoToAgent()
 * 4. UI components use Agent type
 *
 * **Key Differences from Agent:**
 * - No `deploymentId` field (added during conversion)
 * - No `config` field (fetched separately when needed)
 * - No `supportedConfigs` (computed during conversion)
 * - Includes permission metadata (permission_level, owner_id)
 *
 * **Related Types:**
 * - {@link Agent} - Rich format for frontend (this gets converted to Agent)
 * - {@link DiscoveryResponse} - Contains array of AssistantInfo
 *
 * @see apps/langconnect/langconnect/api/mirror_apis.py - Backend implementation
 */
export interface AssistantInfo {
  assistant_id: string;
  graph_id: string;
  name: string;
  description?: string | null;
  tags?: string[];
  permission_level: "owner" | "editor" | "viewer" | "admin";
  allowed_actions?: string[];  // Backend-provided allowed actions (Phase 4)
  owner_id: string;
  owner_display_name?: string;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

/**
 * AgentDisplayItem - Unified display format for admin UI.
 *
 * This type enables the admin dashboard to show both graphs (templates)
 * and assistants (instances) in a single unified list.
 *
 * **Why this type exists:**
 * - Admin dashboard needs to show graphs AND assistants together
 * - Enables grouping assistants by their graph template
 * - Provides consistent interface for permission management UI
 *
 * **Usage:**
 * - Used by admin-dashboard.tsx (statistics and overview)
 * - Used by add-permission-modal.tsx (grouped assistant selection)
 * - Created by mergeGraphsAndAssistants() in AgentsProvider
 * - Stored in AgentsProvider.displayItems state
 *
 * **Data Flow:**
 * 1. AgentsProvider receives GraphInfo[] and AssistantInfo[]
 * 2. mergeGraphsAndAssistants() creates AgentDisplayItem[]
 * 3. Admin components consume displayItems from context
 *
 * **Type Discrimination:**
 * - `type: "graph"` - Represents a graph template (shows in admin view only)
 * - `type: "assistant"` - Represents an assistant instance
 *
 * **Key Differences from Agent:**
 * - Simplified structure (no config, metadata, version fields)
 * - Can represent both graphs and assistants (discriminated union)
 * - Includes UI-specific fields (assistants_count, needs_initialization)
 *
 * **Related Types:**
 * - {@link Agent} - Full agent representation (used by 80% of components)
 * - {@link GraphInfo} - Graph metadata (merged into AgentDisplayItem)
 * - {@link AssistantInfo} - Assistant metadata (merged into AgentDisplayItem)
 *
 * **Important Note:**
 * Only 20% of components use this type (admin components). Most components
 * use the Agent type directly. Do not use AgentDisplayItem for general UI
 * components - it lacks necessary fields like config and metadata.
 *
 * @see apps/web/src/providers/Agents.tsx:mergeGraphsAndAssistants() - Creation function
 */
export interface AgentDisplayItem {
  id: string;
  type: "graph" | "assistant";
  name: string;
  description?: string;
  tags?: string[];
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

/**
 * Assistant Version History Types
 */

export interface AssistantVersion {
  version: number;
  name: string;
  description?: string;
  config: Record<string, any>;
  metadata?: Record<string, any>;
  tags?: string[];
  commit_message?: string;
  created_by?: string;
  created_by_display_name?: string;
  created_at: string;
  is_latest: boolean;
}

export interface AssistantVersionsResponse {
  assistant_id: string;
  assistant_name: string;
  versions: AssistantVersion[];
  total_versions: number;
  latest_version: number;
}

export interface RestoreVersionRequest {
  version: number;
  commit_message?: string;
}

export interface RestoreVersionResponse {
  assistant_id: string;
  restored_from_version: number;
  new_version: number;
  success: boolean;
  message: string;
}
