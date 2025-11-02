import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';

/**
 * On-demand signed URL generation for images
 *
 * This proxy route generates fresh signed URLs for storage paths on every request,
 * solving the expiry problem where preview_url expires after 30 minutes.
 *
 * Usage:
 *   <img src="/api/langconnect/storage/image?path={storage_path}" />
 *
 * Query params:
 *   - path: Storage path (e.g., "uuid/timestamp_filename.png")
 *   - bucket: Optional bucket name (defaults to "chat-uploads")
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const storagePath = searchParams.get('path');
    const bucket = searchParams.get('bucket') || 'chat-uploads';

    if (!storagePath) {
      return NextResponse.json(
        { error: 'Missing storage path' },
        { status: 400 }
      );
    }

    // Get authenticated Supabase client
    const supabase = await createClient();

    // Check authentication
    const { data: { session }, error: authError } = await supabase.auth.getSession();
    if (authError || !session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Generate signed URL with 1 hour expiry
    const { data, error } = await supabase
      .storage
      .from(bucket)
      .createSignedUrl(storagePath, 3600); // 1 hour expiry

    if (error) {
      console.error('Failed to generate signed URL:', error);
      return NextResponse.json(
        { error: 'Failed to generate signed URL', details: error.message },
        { status: 500 }
      );
    }

    if (!data?.signedUrl) {
      return NextResponse.json(
        { error: 'No signed URL returned' },
        { status: 500 }
      );
    }

    // Fetch the actual image from Supabase Storage
    const imageResponse = await fetch(data.signedUrl);

    if (!imageResponse.ok) {
      console.error('Failed to fetch image from storage:', imageResponse.statusText);
      return NextResponse.json(
        { error: 'Failed to fetch image from storage' },
        { status: imageResponse.status }
      );
    }

    // Get image data
    const imageBuffer = await imageResponse.arrayBuffer();

    // Determine content type from storage path or response
    const contentType = imageResponse.headers.get('content-type') || 'image/png';

    // Return image with caching headers
    return new NextResponse(imageBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400', // Cache for 1 hour, allow stale for 24 hours
      },
    });

  } catch (error) {
    console.error('Image proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
