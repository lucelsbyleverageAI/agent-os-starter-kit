/**
 * LangGraph Individual Cron Job API Routes
 *
 * Routes for managing individual cron jobs:
 * - GET /api/langgraph/crons/[cronId] - Get cron job details
 * - PATCH /api/langgraph/crons/[cronId] - Update cron job
 * - DELETE /api/langgraph/crons/[cronId] - Delete cron job
 */

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/client";
import { auth } from "@/lib/auth/auth";

export const runtime = "edge";

type RouteParams = {
  params: Promise<{
    cronId: string;
  }>;
};

/**
 * GET /api/langgraph/crons/[cronId]
 * Get details of a specific cron job
 */
export async function GET(
  req: NextRequest,
  { params }: RouteParams
) {
  try {
    const session = await auth();
    if (!session?.accessToken) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const { cronId } = await params;
    const { searchParams } = new URL(req.url);
    const deploymentId = searchParams.get("deploymentId");

    if (!deploymentId) {
      return NextResponse.json(
        { error: "deploymentId is required" },
        { status: 400 }
      );
    }

    const client = createClient(deploymentId, session.accessToken);

    // Get the cron job
    const cron = await client.crons.get(cronId);

    return NextResponse.json({ cron });
  } catch (error: any) {
    console.error(`[crons:get] error:`, error);
    return NextResponse.json(
      { error: error.message || "Failed to get cron job" },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/langgraph/crons/[cronId]
 * Update a cron job (e.g., pause/resume, update schedule)
 *
 * Body:
 * - deploymentId: string (required)
 * - schedule: string (optional) - new cron expression
 * - input: object (optional) - new input
 * - metadata: object (optional) - new metadata
 */
export async function PATCH(
  req: NextRequest,
  { params }: RouteParams
) {
  try {
    const session = await auth();
    if (!session?.accessToken) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const { cronId } = await params;
    const body = await req.json();
    const { deploymentId, ...updateData } = body;

    if (!deploymentId) {
      return NextResponse.json(
        { error: "deploymentId is required" },
        { status: 400 }
      );
    }

    const client = createClient(deploymentId, session.accessToken);

    // Update the cron job
    const cron = await client.crons.update(cronId, updateData);

    return NextResponse.json({
      cron,
      message: "Cron job updated successfully"
    });
  } catch (error: any) {
    console.error(`[crons:update] error:`, error);
    return NextResponse.json(
      { error: error.message || "Failed to update cron job" },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/langgraph/crons/[cronId]
 * Delete a cron job
 */
export async function DELETE(
  req: NextRequest,
  { params }: RouteParams
) {
  try {
    const session = await auth();
    if (!session?.accessToken) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const { cronId } = await params;
    const { searchParams } = new URL(req.url);
    const deploymentId = searchParams.get("deploymentId");

    if (!deploymentId) {
      return NextResponse.json(
        { error: "deploymentId is required" },
        { status: 400 }
      );
    }

    const client = createClient(deploymentId, session.accessToken);

    // Delete the cron job
    await client.crons.delete(cronId);

    return NextResponse.json({
      success: true,
      message: "Cron job deleted successfully"
    });
  } catch (error: any) {
    console.error(`[crons:delete] error:`, error);
    return NextResponse.json(
      { error: error.message || "Failed to delete cron job" },
      { status: 500 }
    );
  }
}
