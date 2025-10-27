import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * GET /api/langconnect/storage/signed-url
 *
 * Proxy endpoint to get signed URLs for accessing images in storage.
 *
 * Query params:
 *   - storage_path: Storage URI (e.g., storage://collections/{uuid}/{filename})
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const storagePath = searchParams.get('storage_path');

    if (!storagePath) {
      return NextResponse.json(
        { error: 'storage_path query parameter is required' },
        { status: 400 }
      );
    }

    // Get user session
    const supabase = await createClient();
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Call backend API
    const backendUrl = `${process.env.LANGCONNECT_BASE_URL}/storage/signed-url?storage_path=${encodeURIComponent(storagePath)}`;

    const response = await fetch(backendUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${session.access_token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to fetch signed URL' }));
      return NextResponse.json(
        errorData,
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Error in signed URL proxy:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
