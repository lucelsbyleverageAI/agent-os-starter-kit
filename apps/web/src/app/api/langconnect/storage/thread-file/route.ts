import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * GET /api/langconnect/storage/thread-file
 *
 * Proxy endpoint to download files from thread outputs.
 * Validates user owns the thread before allowing access.
 *
 * Query params:
 *   - storage_path: Storage path (user_id/thread_id/filename)
 *   - bucket: Storage bucket (default: agent-outputs)
 */
export async function GET(request: NextRequest) {
  try {
    // Get user session
    const supabase = await createClient();
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Get query params
    const { searchParams } = new URL(request.url);
    const storagePath = searchParams.get('storage_path');
    const bucket = searchParams.get('bucket') || 'agent-outputs';

    if (!storagePath) {
      return NextResponse.json(
        { error: 'storage_path query parameter is required' },
        { status: 400 }
      );
    }

    // Call backend API
    const backendUrl = new URL(`${process.env.LANGCONNECT_BASE_URL}/storage/thread-file`);
    backendUrl.searchParams.set('storage_path', storagePath);
    backendUrl.searchParams.set('bucket', bucket);

    const response = await fetch(backendUrl.toString(), {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${session.access_token}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to fetch file' }));
      return NextResponse.json(
        errorData,
        { status: response.status }
      );
    }

    // Stream the file response back
    const contentType = response.headers.get('content-type') || 'application/octet-stream';
    const contentDisposition = response.headers.get('content-disposition');

    const headers: HeadersInit = {
      'Content-Type': contentType,
    };

    if (contentDisposition) {
      headers['Content-Disposition'] = contentDisposition;
    }

    const blob = await response.blob();
    return new NextResponse(blob, {
      status: 200,
      headers,
    });

  } catch (error) {
    console.error('Error in thread file proxy:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
