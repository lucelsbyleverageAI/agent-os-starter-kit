import { Agent } from "@/types/agent";
import { Deployment } from "@/types/deployment";

// Minimal agent type for display purposes
type MinimalAgent = {
  assistant_id: string;
  graph_id: string;
  name: string;
  description?: string;
  deploymentId: string;
  tags?: string[];
  updated_at?: string;
  metadata?: any;
  permission_level?: 'owner' | 'editor' | 'viewer' | 'admin';
  allowed_actions?: string[];
};

export interface GraphGroup {
  agents: (Agent | MinimalAgent)[];
  deployment: Deployment;
  graphId: string;
}
