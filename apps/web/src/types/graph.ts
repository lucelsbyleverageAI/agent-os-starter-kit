export interface GraphNode {
  id: string;
  type?: "runnable";
  data?: {
    name: string;
  };
}

export interface GraphEdge {
  source: string;
  target: string;
  conditional?: boolean;
}

export interface GraphSchema {
  nodes: GraphNode[];
  edges: GraphEdge[];
} 