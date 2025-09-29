import { NextRequest, NextResponse } from "next/server";
import { getDeployments } from "@/lib/environment/deployments";

export const runtime = "edge";

/**
 * Performance timing utility for debugging
 */
class PerformanceTimer {
  private startTime: number;
  private measurements: Array<{
    operation: string;
    duration: number;
    timestamp: number;
  }> = [];

  constructor() {
    this.startTime = Date.now();
  }

  measure(operation: string, startTime: number): void {
    const duration = Date.now() - startTime;
    this.measurements.push({
      operation,
      duration,
      timestamp: Date.now() - this.startTime
    });
  }

  getResults() {
    const totalDuration = Date.now() - this.startTime;
    return {
      total_duration: totalDuration,
      measurements: this.measurements,
      summary: this.measurements.map(m => `${m.operation}: ${m.duration}ms`).join(', ')
    };
  }
}

/**
 * Extract user ID from JWT access token
 * This is a simplified approach for the discovery endpoint
 */
function extractUserIdFromToken(accessToken: string): string | null {
  try {
    // JWT tokens have 3 parts separated by dots: header.payload.signature
    const parts = accessToken.split('.');
    if (parts.length !== 3) {
      return null;
    }
    
    // Decode the payload (second part)
    const payload = JSON.parse(atob(parts[1]));
    
    // Standard JWT claim for user ID (could be 'sub', 'user_id', etc.)
    return payload.sub || payload.user_id || payload.id || null;
  } catch (_error) {
    return null;
  }
}

/**
 * Permission-aware graph and assistant discovery endpoint.
 * 
 * Replaces the complex /api/langgraph/defaults endpoint with a clean,
 * permission-aware system that uses our LangConnect backend.
 * 
 * Returns only graphs and assistants the user has permission to access.
 */
export async function GET(req: NextRequest) {
  const timer = new PerformanceTimer();
  const _requestId = Math.random().toString(36).substring(2, 8);
  
  try {
    const url = new URL(req.url);
    const deploymentId = url.searchParams.get("deploymentId");
    const accessToken = req.headers.get("Authorization")?.replace("Bearer ", "");

    if (!deploymentId) {
      return NextResponse.json(
        { error: "Missing deploymentId parameter" },
        { status: 400 }
      );
    }

    if (!accessToken) {
      return NextResponse.json(
        { error: "Authorization required" },
        { status: 401 }
      );
    }

    // Get deployment configuration
    const deployments = getDeployments();
    const deployment = deployments.find((d) => d.id === deploymentId);
    
    if (!deployment) {
      return NextResponse.json(
        { error: "Deployment not found" },
        { status: 404 }
      );
    }

    const baseApiUrl = process.env.NEXT_PUBLIC_LANGCONNECT_API_URL;
    if (!baseApiUrl) {
      throw new Error(
        "LangConnect API URL not configured. Please set NEXT_PUBLIC_LANGCONNECT_API_URL"
      );
    }

    const headers = {
      "Authorization": `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    };

    // STEP 1: Get user-accessible graphs with permissions (mirror-backed)
    const graphsStart = Date.now();
    const graphsResponse = await fetch(`${baseApiUrl}/agents/mirror/graphs`, { headers });
    timer.measure("accessible_graphs", graphsStart);
    
    if (!graphsResponse.ok) {
      const errorText = await graphsResponse.text();
      throw new Error(`Accessible graphs fetch failed: ${graphsResponse.status} ${errorText}`);
    }

    const graphsResults = await graphsResponse.json();
                
    // STEP 2: Fetch current assistants (mirror-backed)
    const assistantsStart = Date.now();
    const assistantsResponse = await fetch(`${baseApiUrl}/agents/mirror/assistants`, { headers });
    timer.measure("fetch_assistants_initial", assistantsStart);
    
    if (!assistantsResponse.ok) {
      const errorText = await assistantsResponse.text();
      throw new Error(`Assistants fetch failed: ${assistantsResponse.status} ${errorText}`);
    }

    const assistantsData = await assistantsResponse.json();

    // STEP 3: Discovery Complete - No Enhancement Logic
    // The simplified /graphs/scan endpoint no longer provides enhancement detection
    
    const currentUserId = accessToken ? extractUserIdFromToken(accessToken) : null;

    // Build response
    const responseData = {
      valid_graphs: graphsResults.graphs || [],
      invalid_graphs: [],
      assistants: assistantsData.assistants || [],
      user_role: 'user',
      is_dev_admin: false,
      scan_metadata: {
        langgraph_graphs_found: graphsResults.graphs?.length || 0,
        valid_graphs: graphsResults.graphs?.length || 0,
        invalid_graphs: 0,
        scan_duration_ms: timer.getResults().measurements.find(m => m.operation === "accessible_graphs")?.duration || 0
      },
      assistant_counts: {
        total: assistantsData.total_count || 0,
        owned: assistantsData.owned_count || 0,
        shared: assistantsData.shared_count || 0,
      },
      deployment_id: deploymentId,
      deployment_name: deployment.name,
      debug_info: {
        enhancement_note: "Enhancement logic moved to admin endpoint /admin/initialize-platform",
        graphs_discovered: graphsResults.graphs?.length || 0,
        assistants_discovered: assistantsData.assistants?.length || 0,
        current_user_id: currentUserId,
        ...timer.getResults()
      }
    };
                                                    
    return NextResponse.json(responseData, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unknown error",
        details: "Check server logs for more information",
        debug_info: timer.getResults()
      },
      { status: 500 }
    );
  }
} 