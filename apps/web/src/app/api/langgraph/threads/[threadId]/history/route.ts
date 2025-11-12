import { NextRequest, NextResponse } from "next/server";
import { createClient as createSupabaseClient } from "@/lib/supabase/server";

/**
 * GET /api/langgraph/threads/[threadId]/history
 *
 * Fetches thread history for deprecated threads using service account credentials.
 * This bypasses the user JWT authorization that fails for threads belonging to deleted assistants.
 *
 * Security:
 * - Requires user authentication
 * - Validates user has historical access to the thread via LangConnect API
 * - Uses service account credentials server-side only
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ threadId: string }> }
) {
  try {
    const { threadId } = await params;
    const { searchParams } = request.nextUrl;
    const deploymentId = searchParams.get("deploymentId");

    if (!deploymentId) {
      return NextResponse.json(
        { error: "Missing deploymentId parameter" },
        { status: 400 }
      );
    }

    // Verify user is authenticated
    const supabase = await createSupabaseClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    // Get access token for LangConnect API call
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.access_token) {
      return NextResponse.json(
        { error: "No access token available" },
        { status: 401 }
      );
    }

    // Verify user has access to this thread via LangConnect API
    const baseApiUrl = process.env.NEXT_PUBLIC_LANGCONNECT_API_URL;
    if (!baseApiUrl) {
      throw new Error(
        "LangConnect API URL not configured. Please set NEXT_PUBLIC_LANGCONNECT_API_URL"
      );
    }

    const threadValidationUrl = `${baseApiUrl}/agents/mirror/threads?thread_id=${threadId}`;
    const threadValidationResponse = await fetch(threadValidationUrl, {
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
    });

    if (!threadValidationResponse.ok) {
      console.error(
        "[ThreadHistory] Thread validation failed:",
        threadValidationResponse.status
      );
      return NextResponse.json(
        { error: "Thread not found or access denied" },
        { status: 404 }
      );
    }

    const threadValidationData = await threadValidationResponse.json();
    const threads = threadValidationData.threads || [];

    if (threads.length === 0) {
      console.error("[ThreadHistory] Thread not found in mirror:", threadId);
      return NextResponse.json(
        { error: "Thread not found or access denied" },
        { status: 404 }
      );
    }

    // Get deployment URL for direct API access
    const deployment = require("@/lib/environment/deployments").getDeployments().find(
      (d: any) => d.id === deploymentId
    );

    if (!deployment) {
      return NextResponse.json(
        { error: "Deployment not found" },
        { status: 404 }
      );
    }

    // Use service account key for authorization (bypasses user JWT checks)
    const langsmithApiKey = process.env.LANGSMITH_API_KEY;
    if (!langsmithApiKey) {
      throw new Error("LANGSMITH_API_KEY not configured");
    }

    // Call LangGraph search endpoint directly with service account credentials
    // The TypeScript SDK doesn't expose the 'ids' parameter, so we use fetch
    // Uses x-auth-scheme: langsmith to enable service account mode
    const searchUrl = `${deployment.deploymentUrl}/threads/search`;
    const searchResponse = await fetch(searchUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-auth-scheme": "langsmith",
        "x-api-key": langsmithApiKey,
      },
      body: JSON.stringify({
        ids: [threadId],
        metadata: {},
        values: {},
        status: "idle",
        limit: 10,
        offset: 0,
        sort_by: "thread_id",
        sort_order: "asc",
        select: ["thread_id", "metadata", "values"],
      }),
    });

    if (!searchResponse.ok) {
      const errorText = await searchResponse.text();
      console.error("[ThreadHistory] LangGraph search failed:", {
        status: searchResponse.status,
        error: errorText,
      });
      return NextResponse.json(
        { error: "Thread not found in LangGraph", details: errorText },
        { status: 404 }
      );
    }

    const searchResult = await searchResponse.json();

    if (!searchResult || searchResult.length === 0) {
      return NextResponse.json(
        { error: "Thread not found in LangGraph" },
        { status: 404 }
      );
    }

    const thread = searchResult[0];

    // Return in history-compatible format
    return NextResponse.json({
      values: [thread.values],
    });
  } catch (error: any) {
    console.error("[ThreadHistory] Error fetching thread history:", {
      error: error.message,
      stack: error.stack,
    });

    return NextResponse.json(
      { error: "Failed to fetch thread history", details: error.message },
      { status: 500 }
    );
  }
}
