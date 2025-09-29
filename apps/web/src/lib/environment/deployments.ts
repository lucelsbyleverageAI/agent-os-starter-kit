import { Deployment } from "@/types/deployment";

/**
 * Loads the deployment configuration from individual environment variables.
 * @returns {Deployment[]} The list of deployments (always contains a single deployment).
 */
export function getDeployments(): Deployment[] {
  // Get individual deployment configuration from environment variables
  const deploymentId = process.env.NEXT_PUBLIC_LANGGRAPH_DEPLOYMENT_ID;
  const deploymentUrl = process.env.NEXT_PUBLIC_LANGGRAPH_API_URL;
  const tenantId = process.env.NEXT_PUBLIC_LANGGRAPH_TENANT_ID;
  const defaultGraphId = process.env.NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID;
  
  // Fallback to legacy API URL if deployment URL is not set
  const finalDeploymentUrl = deploymentUrl || process.env.NEXT_PUBLIC_LANGGRAPH_API_URL;
  
  // Use defaults for missing values (useful for build time and local development)
  const deployment: Deployment = {
    id: deploymentId || "default",
    deploymentUrl: finalDeploymentUrl || "http://localhost:2024",
    tenantId: tenantId || "default",
    name: "Production",
    isDefault: true,
    defaultGraphId: defaultGraphId || "tools_agent"
  };

  // Validate required fields
  if (!deployment.deploymentUrl) {
    console.warn("No deployment URL configured, using default");
    deployment.deploymentUrl = "http://localhost:2024";
  }
  
  if (!deployment.defaultGraphId) {
    console.warn("No default graph ID configured, using 'tools_agent'");
    deployment.defaultGraphId = "tools_agent";
  }
  
  return [deployment];
}
