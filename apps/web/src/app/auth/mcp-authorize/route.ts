import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from '@supabase/ssr';
import * as Sentry from '@sentry/nextjs';

/**
 * OAuth 2.1 Authorization endpoint for MCP clients.
 * Handles authorization code flow with PKCE support.
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  
  try {
    // Extract OAuth parameters
    const response_type = searchParams.get("response_type");
    const client_id = searchParams.get("client_id");
    const redirect_uri = searchParams.get("redirect_uri");
    const scope = searchParams.get("scope") || "openid email profile";
    const state = searchParams.get("state");
    const code_challenge = searchParams.get("code_challenge");
    const code_challenge_method = searchParams.get("code_challenge_method");
    const client_name = searchParams.get("client_name") || "MCP Client";

    // Add Sentry breadcrumb for OAuth authorization request
    Sentry.addBreadcrumb({
      message: 'OAuth Authorization Request Received',
      category: 'auth.oauth',
      level: 'info',
      data: {
        response_type,
        client_id,
        client_name,
        redirect_uri,
        scope,
        has_state: !!state,
        has_code_challenge: !!code_challenge,
        code_challenge_method
      }
    });

    // Validate required parameters
    if (!response_type || response_type !== "code") {
      Sentry.captureMessage('OAuth Authorization: Invalid response_type', {
        level: 'warning',
        tags: { context: 'oauth_validation' },
        extra: { response_type, client_id, redirect_uri }
      });
      return redirectWithError(redirect_uri, "invalid_request", "response_type must be 'code'", state);
    }

    if (!client_id) {
      Sentry.captureMessage('OAuth Authorization: Missing client_id', {
        level: 'warning',
        tags: { context: 'oauth_validation' },
        extra: { response_type, redirect_uri }
      });
      return redirectWithError(redirect_uri, "invalid_request", "client_id is required", state);
    }

    if (!redirect_uri) {
      Sentry.captureMessage('OAuth Authorization: Missing redirect_uri', {
        level: 'warning',
        tags: { context: 'oauth_validation' },
        extra: { response_type, client_id }
      });
      return NextResponse.json(
        {
          error: "invalid_request",
          error_description: "redirect_uri is required"
        },
        { status: 400 }
      );
    }

    // Validate redirect URI - allow HTTPS or localhost
    const isValidRedirectUri = (uri: string): boolean => {
      try {
        const url = new URL(uri);
        if (url.protocol === 'https:') return true;
        if (url.protocol === 'http:' && (url.hostname === 'localhost' || url.hostname === '127.0.0.1')) return true;
        return false;
      } catch {
        return false;
      }
    };

    if (!isValidRedirectUri(redirect_uri)) {
      Sentry.captureMessage('OAuth Authorization: Invalid redirect_uri format', {
        level: 'warning',
        tags: { context: 'oauth_validation' },
        extra: { client_id, redirect_uri }
      });
      
      return NextResponse.json(
        {
          error: "invalid_request", 
          error_description: "Invalid redirect_uri - must be HTTPS or localhost"
        },
        { status: 400 }
      );
    }

    // Validate PKCE parameters (recommended for public clients)
    if (code_challenge && (!code_challenge_method || code_challenge_method !== "S256")) {
      return redirectWithError(redirect_uri, "invalid_request", "code_challenge_method must be S256", state);
    }

    // Check if user is authenticated via Supabase
    let isAuthenticated = false;
    let user = null;
    let supabaseAccessToken = null;
    
    try {
      const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
      const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
      
      if (supabaseUrl && supabaseAnonKey) {
        const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
          cookies: {
            get(name: string) {
              return request.cookies.get(name)?.value;
            },
            set() {},
            remove() {},
          },
        });
        
        const { data: { user: sessionUser } } = await supabase.auth.getUser();
        const { data: { session } } = await supabase.auth.getSession();
        
        user = sessionUser;
        isAuthenticated = !!user;
        supabaseAccessToken = session?.access_token || null;
        

      }
    } catch (_error) {
      isAuthenticated = false;
    }
    
    // Generate authorization code and encode auth data
    const authCode = `mcp_auth_${Date.now()}_${Math.random().toString(36).substring(7)}`;
    const authData = {
      client_id,
      redirect_uri,
      scope,
      code_challenge,
      code_challenge_method,
      created_at: Date.now(),
      expires_at: Date.now() + (10 * 60 * 1000), // 10 minutes
      user_id: user?.id || null,
      user_email: user?.email || null,
      supabase_access_token: supabaseAccessToken,
    };

    const encodedAuthData = Buffer.from(JSON.stringify(authData)).toString('base64url');
    const fullAuthCode = `${authCode}.${encodedAuthData}`;

    if (!isAuthenticated) {
      // User not authenticated - redirect to login page
      Sentry.addBreadcrumb({
        message: 'OAuth Authorization: User not authenticated, redirecting to login',
        category: 'auth.oauth',
        level: 'info',
        data: { client_id, client_name, redirect_uri }
      });

      const frontendBaseUrl = process.env.NEXT_PUBLIC_FRONTEND_BASE_URL || 
                             process.env.FRONTEND_BASE_URL || 
                             'http://localhost:3000';
      const loginUrl = new URL('/auth/mcp-login', frontendBaseUrl);
      loginUrl.searchParams.set('client_id', client_id);
      loginUrl.searchParams.set('client_name', client_name || "MCP Client");
      loginUrl.searchParams.set('redirect_uri', redirect_uri);
      loginUrl.searchParams.set('scope', scope);
      loginUrl.searchParams.set('state', state || '');
      loginUrl.searchParams.set('code_challenge', code_challenge || '');
      loginUrl.searchParams.set('code_challenge_method', code_challenge_method || '');
      
      // Set resource URL for MCP server
      const inferredOrigin = `${request.nextUrl.protocol}//${request.nextUrl.host}`;
      const publicMcpBase = process.env.NEXT_PUBLIC_MCP_SERVER_URL || process.env.MCP_PUBLIC_BASE_URL || inferredOrigin;
      const canonicalResource = new URL('/mcp', publicMcpBase).toString().replace(/\/$/, "");
      loginUrl.searchParams.set('resource', canonicalResource);
      
      Sentry.addBreadcrumb({
        message: 'OAuth Authorization: Redirecting to MCP login page',
        category: 'auth.oauth',
        level: 'info',
        data: { 
          loginUrl: loginUrl.toString(),
          frontendBaseUrl,
          publicMcpBase,
          canonicalResource
        }
      });
      
      return NextResponse.redirect(loginUrl);
    }

    // User is authenticated - redirect back to client with authorization code
    Sentry.addBreadcrumb({
      message: 'OAuth Authorization: User authenticated, generating authorization code',
      category: 'auth.oauth',
      level: 'info',
      data: { 
        user_id: user?.id,
        client_id,
        redirect_uri,
        has_supabase_token: !!supabaseAccessToken
      }
    });

    
    const callbackUrl = new URL(redirect_uri);
    callbackUrl.searchParams.set('code', fullAuthCode);
    if (state) {
      callbackUrl.searchParams.set('state', state);
    }

    Sentry.addBreadcrumb({
      message: 'OAuth Authorization: Redirecting to client callback with authorization code',
      category: 'auth.oauth',
      level: 'info',
      data: { 
        callbackUrl: callbackUrl.toString(),
        codeLength: fullAuthCode.length,
        hasState: !!state
      }
    });

    return NextResponse.redirect(callbackUrl);

  } catch (error) {
    console.error("Authorization error:", error);
    
    Sentry.captureException(error, {
      tags: { context: 'oauth_authorization' },
      extra: {
        client_id: searchParams.get("client_id"),
        redirect_uri: searchParams.get("redirect_uri"),
        response_type: searchParams.get("response_type")
      }
    });
    
    return redirectWithError(
      searchParams.get("redirect_uri"), 
      "server_error", 
      "Internal server error", 
      searchParams.get("state")
    );
  }
}

/**
 * Helper function to redirect with OAuth error
 */
function redirectWithError(redirect_uri: string | null, error: string, error_description: string, state: string | null) {
  if (!redirect_uri) {
    return NextResponse.json(
      { error, error_description },
      { status: 400 }
    );
  }

  try {
    const errorUrl = new URL(redirect_uri);
    errorUrl.searchParams.set('error', error);
    errorUrl.searchParams.set('error_description', error_description);
    if (state) {
      errorUrl.searchParams.set('state', state);
    }
    
    return NextResponse.redirect(errorUrl);
  } catch {
    return NextResponse.json(
      { error, error_description },
      { status: 400 }
    );
  }
}

// Handle unsupported methods
export async function POST() {
  return NextResponse.json(
    {
      error: "invalid_request",
      error_description: "POST method not supported for authorization endpoint"
    },
    { status: 405 }
  );
}
