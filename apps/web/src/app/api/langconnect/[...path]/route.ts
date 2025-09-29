import { NextRequest, NextResponse } from "next/server";

// export const runtime = "edge"; // Disabled for FormData streaming support

/**
 * Generic proxy route for LangConnect API requests.
 * 
 * This route forwards all requests to the LangConnect backend server,
 * preserving the original path, method, headers, query parameters, and body.
 * 
 * Usage:
 * - GET /api/langconnect/agents/graphs/tools_agent/permissions
 * - POST /api/langconnect/agents/assistants  
 * - DELETE /api/langconnect/agents/graphs/tools_agent/permissions/user123
 * 
 * All requests are forwarded to: ${LANGCONNECT_BASE_URL}/{...path}
 */

async function handleRequest(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    // Use internal LangConnect URL for server-side operations, fallback to public URL
    const baseApiUrl = process.env.LANGCONNECT_BASE_URL || process.env.NEXT_PUBLIC_LANGCONNECT_API_URL;
    if (!baseApiUrl) {
      throw new Error(
        "LangConnect API URL not configured. Please set LANGCONNECT_BASE_URL or NEXT_PUBLIC_LANGCONNECT_API_URL"
      );
    }

    // Await params before using them
    const resolvedParams = await params;
    
    // Extract the path from the dynamic route
    const requestPath = resolvedParams.path.join('/');
    
    // Build the target URL
    const targetUrl = new URL(requestPath, baseApiUrl);
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    
    // Preserve query parameters
    const url = new URL(req.url);
    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    // Extract headers (excluding host-specific ones)
    const headers: Record<string, string> = {};
    
    req.headers.forEach((value, key) => {
      // Forward most headers but exclude host-specific ones that will be recalculated
      // Always exclude these headers as they will be set by fetch
      const shouldExclude = ['host', 'connection', 'content-length'].includes(key.toLowerCase());
      
      if (!shouldExclude) {
        headers[key] = value;
      }
    });



    // Build the request options
    const requestOptions: RequestInit = {
      method: req.method,
      headers: {...headers},
    };

    // Add body for non-GET requests
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      const contentType = req.headers.get('content-type');
      
      if (contentType && contentType.includes('multipart/form-data')) {
        // For FormData (file uploads), use a streaming approach to preserve the exact multipart structure
                        
        try {
          // Get the request body as a stream and convert to buffer
          const bodyBuffer = await req.arrayBuffer();
                    
          // Use the raw buffer as the body to preserve exact multipart boundaries
          requestOptions.body = bodyBuffer;
          
          // Keep the original content-type header with boundary
          // Don't delete it since we're preserving the exact format
          
        } catch (error) {
          console.error('Failed to process FormData:', error);
          throw new Error(`Failed to process FormData: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
      } else if (contentType && contentType.includes('application/json')) {
        // For JSON requests, read as text
        try {
          const body = await req.text();
          if (body) {
            requestOptions.body = body;
          }
        } catch (error) {
          console.warn('Failed to read JSON body:', error);
        }
      } else {
        // For other content types, try to preserve the body
        try {
          requestOptions.body = req.body;
          (requestOptions as any).duplex = 'half';
        } catch (error) {
          console.warn('Failed to read request body:', error);
        }
      }
    }

    // Make the request to LangConnect
    const response = await fetch(targetUrl.toString(), requestOptions);

    // Build the response headers (excluding problematic ones)
    const responseHeaders: Record<string, string> = {};
    response.headers.forEach((value, key) => {
      if (!['connection', 'keep-alive', 'transfer-encoding'].includes(key.toLowerCase())) {
        responseHeaders[key] = value;
      }
    });

    // Attach upstream debug headers
    responseHeaders['x-debug-proxy'] = 'langconnect';
    responseHeaders['x-upstream-url'] = targetUrl.toString();
    responseHeaders['x-upstream-status'] = String(response.status);
    responseHeaders['x-debug-request-id'] = requestId;

    
    // Handle responses with no content (204 No Content)
    if (response.status === 204 || response.status === 304) {
      const r = new NextResponse(null, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
      return r;
    }

    // Get the response data for other status codes
    const responseText = await response.text();

    // Return the response
    const out = new NextResponse(responseText, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
    return out;

  } catch (error) {
    console.error(`❌ LangConnect proxy error for ${req.method} ${(await params).path.join('/')}:`, error);
    
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Proxy request failed",
        details: "Check server logs for more information"
      },
      { status: 500 }
    );
  }
}

// Export handlers for all HTTP methods
export const GET = handleRequest;
export const POST = handleRequest;
export const PUT = handleRequest;
export const PATCH = handleRequest;
export const DELETE = handleRequest;
export const HEAD = handleRequest;
export const OPTIONS = handleRequest; 