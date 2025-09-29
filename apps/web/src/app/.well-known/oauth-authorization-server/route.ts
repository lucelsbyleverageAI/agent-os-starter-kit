import { NextRequest, NextResponse } from 'next/server';

// Ensure this route is always handled dynamically
export const dynamic = 'force-dynamic';
export const revalidate = 0;

/**
 * OAuth 2.1 Authorization Server Metadata endpoint (RFC 8414)
 * This endpoint provides metadata about the OAuth authorization server
 * to enable automatic client configuration and discovery.
 */
export async function GET(request: NextRequest) {
  // Get base URLs from environment
  const frontendBaseUrl = process.env.FRONTEND_BASE_URL || process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;

//
  if (!supabaseUrl) {
    return NextResponse.json(
      { 
        error: 'server_error', 
        error_description: 'Supabase configuration not found' 
      }, 
      { status: 500 }
    );
  }

  // OAuth 2.1 Authorization Server Metadata per RFC 8414
  const metadata = {
    // Required fields
    issuer: supabaseUrl,
    authorization_endpoint: `${frontendBaseUrl}/auth/mcp-authorize`,
    token_endpoint: `${frontendBaseUrl}/auth/mcp-token`,
    
    // Optional but recommended fields
    userinfo_endpoint: `${supabaseUrl}/auth/v1/user`,
    jwks_uri: `${supabaseUrl}/.well-known/jwks.json`,
    registration_endpoint: `${frontendBaseUrl}/auth/mcp-register`,
    
    // Supported capabilities
    response_types_supported: ['code'],
    grant_types_supported: ['authorization_code', 'refresh_token'],
    code_challenge_methods_supported: ['S256'],
    scopes_supported: ['openid', 'email', 'profile', 'mcp:read', 'mcp:write'],
    subject_types_supported: ['public'],
    id_token_signing_alg_values_supported: ['HS256', 'RS256'],
    
    // Claims that may be returned in ID tokens
    claims_supported: [
      'sub', 'aud', 'exp', 'iat', 'iss', 
      'email', 'email_verified', 'name', 'picture', 'role'
    ],
    
    // Additional OAuth 2.1 features
    token_endpoint_auth_methods_supported: ['client_secret_post', 'client_secret_basic', 'none'],
    revocation_endpoint: `${frontendBaseUrl}/auth/mcp-revoke`,
    
    // PKCE is required for OAuth 2.1
    require_pushed_authorization_requests: false,
    pushed_authorization_request_endpoint: undefined,
  };

  return NextResponse.json(metadata, {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    },
  });
}

/**
 * Handle CORS preflight requests
 */
export async function OPTIONS() {
  return NextResponse.json({}, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    },
  });
}
