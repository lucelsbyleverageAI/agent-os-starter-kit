import { NextRequest } from "next/server";
import { getDeployments } from "@/lib/environment/deployments";

/**
 * Fetches the graph schema for a given assistant
 */
async function getGraphSchema(
  deploymentId: string,
  assistantId: string,
  includeSubgraphs: boolean = true,
  accessToken?: string,
) {
  const deployment = getDeployments().find((d) => d.id === deploymentId);
  if (!deployment) {
    throw new Error(`Deployment ${deploymentId} not found`);
  }
  
  try {
    // Build the URL path
    let path = `assistants/${assistantId}/graph`;
    if (includeSubgraphs) {
      path += '?xray=5';
    }
    
    // Build headers based on auth method
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (!accessToken) {
      // Use LangSmith auth
      if (!process.env.LANGSMITH_API_KEY) {
        throw new Error('LANGSMITH_API_KEY not configured');
      }
      headers['x-api-key'] = process.env.LANGSMITH_API_KEY;
      headers['x-auth-scheme'] = 'langsmith';
    } else {
      // Use user auth
      headers['Authorization'] = `Bearer ${accessToken}`;
      headers['x-supabase-access-token'] = accessToken;
    }
    
    // Make the direct API call to LangGraph
    const targetUrl = `${deployment.deploymentUrl.replace(/\/$/, '')}/${path}`;
    const response = await fetch(targetUrl, {
      headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch graph schema: ${response.status} ${response.statusText}`);
    }

    const schema = await response.json();
    return schema;
  } catch (error) {
    throw new Error(`Failed to get graph schema: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * GET handler for the /api/langgraph/graph-schema endpoint
 */
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const deploymentId = url.searchParams.get("deploymentId");
    const assistantId = url.searchParams.get("assistantId");
    const includeSubgraphs = url.searchParams.get("includeSubgraphs") !== "false";
    
    const accessToken = req.headers
      .get("Authorization")
      ?.replace("Bearer ", "");

    if (!deploymentId) {
      return new Response(
        JSON.stringify({ error: "Missing deploymentId parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    if (!assistantId) {
      return new Response(
        JSON.stringify({ error: "Missing assistantId parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const schema = await getGraphSchema(
      deploymentId,
      assistantId,
      includeSubgraphs,
      accessToken || undefined,
    );

    return new Response(JSON.stringify(schema), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
} 