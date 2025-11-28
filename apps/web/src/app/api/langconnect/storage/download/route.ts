import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';

/**
 * On-demand signed URL generation for downloadable files
 *
 * This proxy route generates fresh signed URLs for storage paths on every request,
 * solving the expiry problem where download_url expires after 1 hour.
 *
 * Usage:
 *   GET /api/langconnect/storage/download?path={storage_path}&bucket={bucket_name}
 *
 * Query params:
 *   - path: Storage path (e.g., "user_id/thread_id/filename.docx")
 *   - bucket: Bucket name (e.g., "agent-outputs")
 *   - filename: Optional filename for download (defaults to filename from path)
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const storagePath = searchParams.get('path');
    const bucket = searchParams.get('bucket');
    const filename = searchParams.get('filename');

    if (!storagePath) {
      return NextResponse.json(
        { error: 'Missing storage path' },
        { status: 400 }
      );
    }

    if (!bucket) {
      return NextResponse.json(
        { error: 'Missing bucket name' },
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

    // Generate signed URL with 1 hour expiry (enough for the download to complete)
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

    // Fetch the actual file from Supabase Storage
    const fileResponse = await fetch(data.signedUrl);

    if (!fileResponse.ok) {
      console.error('Failed to fetch file from storage:', fileResponse.statusText);
      return NextResponse.json(
        { error: 'Failed to fetch file from storage' },
        { status: fileResponse.status }
      );
    }

    // Get file data
    const fileBuffer = await fileResponse.arrayBuffer();

    // Determine content type from response or default to octet-stream
    const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';

    // Determine filename for download
    const downloadFilename = filename || storagePath.split('/').pop() || 'download';

    // Return file with download headers
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': `attachment; filename="${downloadFilename}"`,
        'Cache-Control': 'private, no-cache, no-store, must-revalidate', // Don't cache downloads
      },
    });

  } catch (error) {
    console.error('Download proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
