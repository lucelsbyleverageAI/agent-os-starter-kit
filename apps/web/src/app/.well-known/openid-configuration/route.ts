import { NextRequest, NextResponse } from 'next/server';

// Ensure this route is always handled dynamically (no static page data collection)
export const dynamic = 'force-dynamic';
export const revalidate = 0;

/**
 * OpenID Connect Discovery endpoint - returns error indicating OAuth 2.0 support only
 * This helps clients understand that this server only supports OAuth 2.0 Authorization
 * Server Metadata (RFC 8414) and not full OpenID Connect Discovery.
 */
export async function GET(request: NextRequest) {
  const frontendBaseUrl = process.env.FRONTEND_BASE_URL || process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';
  
  return NextResponse.json({
    error: 'unsupported_discovery_method',
    error_description: 'This server only supports OAuth 2.0 Authorization Server Metadata (RFC 8414). Please use /.well-known/oauth-authorization-server instead.',
    oauth_authorization_server_metadata: `${frontendBaseUrl}/.well-known/oauth-authorization-server`
  }, {
    status: 400,
    headers: {
      'Content-Type': 'application/json',
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
