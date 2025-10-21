/**
 * LangGraph Cron Jobs API Routes
 *
 * This module provides proxy routes for managing LangGraph cron jobs.
 * Cron jobs enable scheduled background agent execution.
 *
 * Routes:
 * - GET /api/langgraph/crons?deploymentId=xxx - List all cron jobs
 * - POST /api/langgraph/crons - Create a new cron job
 */

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/client";
import { auth } from "@/lib/auth/auth";

export const runtime = "edge";

/**
 * GET /api/langgraph/crons
 * List all cron jobs for the current user
 */
export async function GET(req: NextRequest) {
  try {
    const session = await auth();
    if (!session?.accessToken) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const { searchParams } = new URL(req.url);
    const deploymentId = searchParams.get("deploymentId");

    if (!deploymentId) {
      return NextResponse.json(
        { error: "deploymentId is required" },
        { status: 400 }
      );
    }

    const client = createClient(deploymentId, session.accessToken);

    // List all cron jobs
    const crons = await client.crons.search();

    return NextResponse.json({
      crons,
      count: crons.length
    });
  } catch (error: any) {
    console.error("[crons:list] error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to list cron jobs" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/langgraph/crons
 * Create a new cron job
 *
 * Body:
 * - deploymentId: string (required)
 * - assistantId: string (required)
 * - schedule: string (required) - cron expression
 * - input: object (optional) - input for the cron
 * - metadata: object (optional) - metadata for the cron
 */
export async function POST(req: NextRequest) {
  try {
    const session = await auth();
    if (!session?.accessToken || !session?.user?.id) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await req.json();
    const { deploymentId, assistantId, schedule, input, metadata } = body;

    if (!deploymentId || !assistantId || !schedule) {
      return NextResponse.json(
        { error: "deploymentId, assistantId, and schedule are required" },
        { status: 400 }
      );
    }

    const client = createClient(deploymentId, session.accessToken);

    // Inject background agent metadata into cron metadata
    const cronMetadata = {
      ...metadata,
      created_by_user: session.user.id,
      is_background_run: true,
      assistant_id: assistantId,
      deployment_id: deploymentId,
    };

    // Create the cron job
    const cron = await client.crons.create(assistantId, {
      schedule,
      input: input || {},
      metadata: cronMetadata,
    });

    return NextResponse.json({
      cron,
      message: "Cron job created successfully"
    });
  } catch (error: any) {
    console.error("[crons:create] error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to create cron job" },
      { status: 500 }
    );
  }
}
