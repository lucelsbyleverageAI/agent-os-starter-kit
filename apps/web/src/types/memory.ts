export interface Memory {
  id: string;
  memory: string; // The actual memory content (normalized from payload.data)
  user_id: string;
  hash: string;
  metadata?: Record<string, any>;
  created_at: string;
  updated_at?: string;
  // Raw payload from the API for full view
  payload?: {
    data: string;
    hash: string;
    user_id: string;
    created_at: string;
    updated_at?: string;
    agent_id?: string;
    run_id?: string;
    metadata?: Record<string, any>;
  };
}

export interface MemoryResponse {
  success: boolean;
  data?: any;
  message?: string;
}

export interface MemoriesListResponse {
  success: boolean;
  data?: {
    results: Memory[];
    total?: number;
    offset?: number;
    limit?: number;
  };
  message?: string;
}
