import { useCallback, useState } from "react";
import { useAuthContext } from "@/providers/Auth";
import { GraphSchema } from "@/types/graph";
import { toast } from "sonner";

// Simple in-memory cache for graph schemas
const graphSchemaCache = new Map<string, GraphSchema>();

export function useGraphSchema() {
  const { session } = useAuthContext();
  const [loading, setLoading] = useState(false);

  const getGraphSchema = useCallback(
    async (
      assistantId: string,
      deploymentId: string,
      includeSubgraphs: boolean = true
    ): Promise<GraphSchema | undefined> => {
      if (!session?.accessToken) {
        toast.error("No access token found", {
          richColors: true,
        });
        return undefined;
      }

      const cacheKey = `${assistantId}:${deploymentId}:graph-schema:${includeSubgraphs}`;
      
      // Check cache first
      if (graphSchemaCache.has(cacheKey)) {
        return graphSchemaCache.get(cacheKey);
      }

      setLoading(true);
      try {
        // Build the URL parameters
        const params = new URLSearchParams({
          deploymentId,
          assistantId,
          includeSubgraphs: includeSubgraphs.toString(),
        });
        
        // Make the API call to our dedicated graph schema endpoint
        const response = await fetch(`/api/langgraph/graph-schema?${params.toString()}`, {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch graph schema: ${response.status}`);
        }

        const schema: GraphSchema = await response.json();
        
        // Cache the result
        graphSchemaCache.set(cacheKey, schema);
        
        return schema;
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        
        if (!errorMessage.includes('Access token must be provided') && 
            !errorMessage.includes('authentication') && 
            !errorMessage.includes('unauthorized')) {
          toast.error("Failed to get graph schema", {
            description: (
              <div className="flex flex-col items-start gap-2">
                <p>
                  Assistant ID:{" "}
                  <span className="font-mono font-semibold">{assistantId}</span>
                </p>
                <p>
                  Deployment ID:{" "}
                  <span className="font-mono font-semibold">{deploymentId}</span>
                </p>
              </div>
            ),
            richColors: true,
          });
        }
        
        return undefined;
      } finally {
        setLoading(false);
      }
    },
    [session?.accessToken]
  );

  const invalidateGraphSchemaCache = useCallback((assistantId: string) => {
    // Remove all cached entries for this assistant
    const keysToDelete = Array.from(graphSchemaCache.keys()).filter(key => 
      key.startsWith(`${assistantId}:`)
    );
    keysToDelete.forEach(key => graphSchemaCache.delete(key));
  }, []);

  const clearAllGraphSchemaCache = useCallback(() => {
    graphSchemaCache.clear();
  }, []);

  return {
    getGraphSchema,
    invalidateGraphSchemaCache,
    clearAllGraphSchemaCache,
    loading,
  };
} 