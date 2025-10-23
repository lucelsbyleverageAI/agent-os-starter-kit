import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * PUT /api/langconnect/collections/[collectionId]/documents/[documentId]/image
 *
 * Proxy endpoint to replace an image document's file.
 *
 * Accepts multipart/form-data with a file field.
 */
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ collectionId: string; documentId: string }> }
) {
  try {
    const { collectionId, documentId } = await params;

    // Get user session
    const supabase = await createClient();
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Get form data from request
    const formData = await request.formData();

    // Forward to backend API
    const backendUrl = `${process.env.LANGCONNECT_BASE_URL}/collections/${collectionId}/documents/${documentId}/image`;

    const response = await fetch(backendUrl, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${session.access_token}`,
      },
      body: formData, // Forward the form data as-is
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to replace image' }));
      return NextResponse.json(
        errorData,
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Error in image replacement proxy:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
