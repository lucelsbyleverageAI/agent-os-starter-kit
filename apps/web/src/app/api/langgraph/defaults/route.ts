import { NextRequest } from "next/server";
import { Client } from "@langchain/langgraph-sdk";
import { getDeployments } from "@/lib/environment/deployments";

/**
 * Creates a client for a specific deployment, using either LangSmith auth or user auth
 */
function createServerClient(deploymentId: string, accessToken?: string) {
  const deployment = getDeployments().find((d) => d.id === deploymentId);
  if (!deployment) {
    throw new Error(`Deployment ${deploymentId} not found`);
  }

  if (!accessToken) {
    // Use LangSmith auth
    const client = new Client({
      apiUrl: deployment.deploymentUrl,
      apiKey: process.env.LANGSMITH_API_KEY,
      defaultHeaders: {
        "x-auth-scheme": "langsmith",
      },
    });
    return client;
  }

  // Use user auth
  const client = new Client({
    apiUrl: deployment.deploymentUrl,
    defaultHeaders: {
      Authorization: `Bearer ${accessToken}`,
      "x-supabase-access-token": accessToken,
    },
  });
  return client;
}

/**
 * Discovers available graphs by analyzing assistants and validating their schemas
 */
async function discoverAvailableGraphs(
  deploymentId: string,
  client: Client
): Promise<string[]> {
  try {
    const allAssistants = await client.assistants.search({ limit: 200 });
    const potentialGraphIds = [...new Set(allAssistants.map(a => a.graph_id))];
    const validGraphs: string[] = [];
    
    for (const graphId of potentialGraphIds) {
      try {
        const testAssistant = allAssistants.find(a => a.graph_id === graphId);
        if (!testAssistant) {
          continue;
        }
        
        await client.assistants.getSchemas(testAssistant.assistant_id);
        validGraphs.push(graphId);
      } catch {
        // Skip invalid graphs
      }
    }
    
    return validGraphs;
    
  } catch (error) {
    throw new Error(`Failed to discover available graphs: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * Validates assistants against available graphs and cleans up orphaned ones
 */
async function validateAndCleanupAssistants(
  assistants: any[],
  availableGraphs: string[],
  client: Client,
  deploymentId: string,
  clientType: "system" | "user"
): Promise<any[]> {
  const validAssistants: any[] = [];
  const orphanedAssistants: any[] = [];
  
  for (const assistant of assistants) {
    if (availableGraphs.includes(assistant.graph_id)) {
      validAssistants.push(assistant);
    } else {
      orphanedAssistants.push(assistant);
    }
  }
  
  if (orphanedAssistants.length > 0) {
    for (const orphaned of orphanedAssistants) {
      try {
        await client.assistants.delete(orphaned.assistant_id);
      } catch {
        // Continue with other deletions
      }
    }
  }
  
  return validAssistants;
}

/**
 * Gets all assistants for cleanup (including custom user assistants)
 */
async function getAllUserAssistants(
  client: Client,
  deploymentId: string
): Promise<any[]> {
  const allUserAssistants = await client.assistants.search({ limit: 200 });
  return allUserAssistants;
}

/**
 * Gets or creates default assistants for a deployment with comprehensive validation and cleanup
 */
async function getOrCreateDefaultAssistants(
  deploymentId: string,
  accessToken?: string,
) {
  const deployment = getDeployments().find((d) => d.id === deploymentId);
  if (!deployment) {
    throw new Error(`Deployment ${deploymentId} not found`);
  }

  // Create clients
  const lsAuthClient = createServerClient(deploymentId);
  const userAuthClient = createServerClient(deploymentId, accessToken);

  const availableGraphs = await discoverAvailableGraphs(deploymentId, lsAuthClient);
  
  if (availableGraphs.length === 0) {
    return [];
  }

  const [systemDefaultAssistants, allUserAssistants] = await Promise.all([
    (async () => {
      const assistants = await lsAuthClient.assistants.search({
        limit: 100,
        metadata: {
          created_by: "system",
        },
      });
      return assistants;
    })(),
    getAllUserAssistants(userAuthClient, deploymentId)
  ]);

  const [validSystemDefaults, validUserAssistants] = await Promise.all([
    validateAndCleanupAssistants(systemDefaultAssistants, availableGraphs, lsAuthClient, deploymentId, "system"),
    validateAndCleanupAssistants(allUserAssistants, availableGraphs, userAuthClient, deploymentId, "user"),
  ]);

  const validUserDefaults = validUserAssistants.filter(a => a.metadata?._x_oap_is_default === true);

  if (!validSystemDefaults.length) {
    return validUserDefaults;
  }

  if (validSystemDefaults.length === validUserDefaults.length) {
    return validUserDefaults;
  }

  const missingDefaultAssistants = validSystemDefaults.filter(
    (assistant) =>
      !validUserDefaults.some((a) => a.graph_id === assistant.graph_id),
  );

  const newUserDefaultAssistantsPromise = missingDefaultAssistants.map(
    async (assistant) => {
      const isDefaultDeploymentAndGraph =
        deployment.isDefault &&
        deployment.defaultGraphId === assistant.graph_id;
      
      const assistantName = `${isDefaultDeploymentAndGraph ? "Default" : "Primary"} Assistant`;
      
      const newAssistant = await userAuthClient.assistants.create({
        graphId: assistant.graph_id,
        name: assistantName,
        metadata: {
          _x_oap_is_default: true,
          description: `${isDefaultDeploymentAndGraph ? "Default" : "Primary"} Assistant`,
          ...(isDefaultDeploymentAndGraph && { _x_oap_is_primary: true }),
        },
      });
      return newAssistant;
    },
  );

  const newUserDefaultAssistants = [
    ...validUserDefaults,
    ...(await Promise.all(newUserDefaultAssistantsPromise)),
  ];

  if (validSystemDefaults.length === newUserDefaultAssistants.length) {
    return newUserDefaultAssistants;
  }

  throw new Error(
    `Failed to create all default assistants for deployment ${deploymentId}. Expected ${validSystemDefaults.length} default assistants, but found/created ${newUserDefaultAssistants.length}.`,
  );
}

/**
 * GET handler for the /api/langgraph/defaults endpoint
 */
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const deploymentId = url.searchParams.get("deploymentId");
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

    const defaultAssistants = await getOrCreateDefaultAssistants(
      deploymentId,
      accessToken || undefined,
    );

    return new Response(JSON.stringify(defaultAssistants), {
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
