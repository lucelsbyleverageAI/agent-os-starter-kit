import { NextRequest, NextResponse } from "next/server";

/**
 * OAuth 2.0 Dynamic Client Registration endpoint for MCP clients.
 * Implements RFC 7591 for client registration without persistent storage.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Validate required fields according to RFC 7591
    const {
      client_name,
      client_uri,
      redirect_uris,
      grant_types = ["authorization_code", "refresh_token"],
      response_types = ["code"],
      scope = "openid email profile",
      token_endpoint_auth_method = "none" // Public client
    } = body;

    // Validate client name
    if (!client_name || typeof client_name !== 'string' || client_name.length < 1 || client_name.length > 100) {
      return NextResponse.json(
        {
          error: "invalid_client_metadata",
          error_description: "client_name is required and must be a valid string (1-100 characters)"
        },
        { 
          status: 400,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
          }
        }
      );
    }

    // Validate redirect URIs
    if (!redirect_uris || !Array.isArray(redirect_uris) || redirect_uris.length === 0) {
      return NextResponse.json(
        {
          error: "invalid_redirect_uri",
          error_description: "redirect_uris is required and must be an array"
        },
        { 
          status: 400,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
          }
        }
      );
    }

    // Validate redirect URIs - allow HTTPS or localhost
    const validRedirectUris = redirect_uris.filter(uri => {
      try {
        const url = new URL(uri);
        if (url.protocol === 'https:') return true;
        if (url.protocol === 'http:' && (url.hostname === 'localhost' || url.hostname === '127.0.0.1')) return true;
        return false;
      } catch {
        return false;
      }
    });

    if (validRedirectUris.length === 0) {
      return NextResponse.json(
        {
          error: "invalid_redirect_uri", 
          error_description: "At least one valid redirect URI is required (HTTPS or localhost)"
        },
        { 
          status: 400,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
          }
        }
      );
    }

    // Generate client ID (no persistent storage needed)
    const client_id = `mcp_client_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
    
    const registration_response = {
      client_id,
      client_name,
      client_uri,
      redirect_uris: validRedirectUris,
      grant_types,
      response_types,
      scope,
      token_endpoint_auth_method,
      client_id_issued_at: Math.floor(Date.now() / 1000),
    };

    return NextResponse.json(registration_response, {
      status: 201,
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      }
    });

  } catch (error) {
    console.error("Client registration error:", error);
    
    return NextResponse.json(
      {
        error: "server_error",
        error_description: "Internal server error during client registration"
      },
      { 
        status: 500,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "*",
        }
      }
    );
  }
}

// Handle CORS preflight requests
export async function OPTIONS() {
  return NextResponse.json({}, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    },
  });
}

// Handle unsupported methods
export async function GET() {
  return NextResponse.json(
    {
      error: "invalid_request",
      error_description: "GET method not supported for client registration"
    },
    { 
      status: 405,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      }
    }
  );
}
