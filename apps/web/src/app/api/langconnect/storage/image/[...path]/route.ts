import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * GET /api/langconnect/storage/image/[...path]
 *
 * Proxy endpoint for serving images from Supabase Storage.
 * This solves the problem of internal Docker URLs (kong:8000) not being accessible from the browser.
 *
 * Flow:
 * 1. Browser requests this endpoint with storage path
 * 2. Verify user authentication
 * 3. Call LangConnect to get signed URL (with permission check)
 * 4. Fetch image from internal Supabase storage
 * 5. Stream response back to browser
 *
 * Example:
 * GET /api/langconnect/storage/image/collections/uuid/file.png
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;
    const storagePath = path.join("/");

    // Reconstruct storage URI
    const storageUri = `storage://collections/${storagePath}`;

    // Get user session
    const supabase = await createClient();
    const {
      data: { session },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError || !session) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Call LangConnect to get signed URL with permission check
    const backendUrl = `${process.env.LANGCONNECT_BASE_URL}/storage/signed-url?storage_path=${encodeURIComponent(storageUri)}`;

    const signedUrlResponse = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
    });

    if (!signedUrlResponse.ok) {
      const errorData = await signedUrlResponse
        .json()
        .catch(() => ({ error: "Failed to get signed URL" }));
      return NextResponse.json(errorData, {
        status: signedUrlResponse.status,
      });
    }

    const { signed_url } = await signedUrlResponse.json();

    // Rewrite internal Docker URLs to work from the host network in development
    // In dev: kong:8000 -> localhost:8000
    // In prod: URLs work as-is because Next.js is in the same Docker network
    let fetchUrl = signed_url;
    if (signed_url.includes("kong:8000")) {
      fetchUrl = signed_url.replace("kong:8000", "localhost:8000");
    }

    // Fetch the actual image from Supabase Storage using the signed URL
    const imageResponse = await fetch(fetchUrl, {
      method: "GET",
    });

    if (!imageResponse.ok) {
      return NextResponse.json(
        { error: "Failed to fetch image" },
        { status: imageResponse.status }
      );
    }

    // Get the image data
    const imageBuffer = await imageResponse.arrayBuffer();

    // Return the image with appropriate headers
    const headers = new Headers();
    const contentType =
      imageResponse.headers.get("content-type") || "image/png";
    headers.set("Content-Type", contentType);

    // Add caching headers
    // If cache-busting param is present (e.g., ?v=timestamp), cache for longer with immutable
    // Otherwise, use shorter cache with revalidation to support image updates
    const url = new URL(request.url);
    const hasCacheBuster = url.searchParams.has("v");

    if (hasCacheBuster) {
      // With cache-busting, we can safely cache for a long time
      headers.set("Cache-Control", "public, max-age=31536000, immutable");
    } else {
      // Without cache-busting, use shorter cache and allow revalidation
      headers.set("Cache-Control", "public, max-age=300, must-revalidate");
    }

    // Preserve other useful headers
    if (imageResponse.headers.has("content-length")) {
      headers.set(
        "Content-Length",
        imageResponse.headers.get("content-length")!
      );
    }
    if (imageResponse.headers.has("etag")) {
      headers.set("ETag", imageResponse.headers.get("etag")!);
    }
    if (imageResponse.headers.has("last-modified")) {
      headers.set(
        "Last-Modified",
        imageResponse.headers.get("last-modified")!
      );
    }

    return new NextResponse(imageBuffer, {
      status: 200,
      headers,
    });
  } catch (error) {
    console.error("Error in image proxy:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
