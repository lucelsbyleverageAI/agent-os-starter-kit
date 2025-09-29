import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import * as Sentry from '@sentry/nextjs';
import jwt from 'jsonwebtoken';

// Ensure Node.js runtime (this route uses Node-only modules like 'crypto' and 'jsonwebtoken')
export const runtime = "nodejs";

/**
 * OAuth 2.1 Token endpoint for MCP clients.
 * Supports:
 * 1. Authorization Code flow: exchanges authorization codes for MCP access tokens
 * 2. Token Exchange (RFC 8693): exchanges Supabase JWTs for MCP access tokens
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.formData();
    
    // Extract token request parameters
    const grant_type = body.get("grant_type")?.toString();
    const code = body.get("code")?.toString();
    const redirect_uri = body.get("redirect_uri")?.toString();
    const client_id = body.get("client_id")?.toString();
    const code_verifier = body.get("code_verifier")?.toString();
    
    // Token exchange parameters (RFC 8693)
    const subject_token = body.get("subject_token")?.toString();
    const subject_token_type = body.get("subject_token_type")?.toString();
    const requested_token_type = body.get("requested_token_type")?.toString();

    // Add Sentry breadcrumb for token exchange request
    Sentry.addBreadcrumb({
      message: 'OAuth Token Exchange Request Received',
      category: 'auth.token',
      level: 'info',
      data: {
        grant_type,
        client_id,
        redirect_uri,
        has_code: !!code,
        has_code_verifier: !!code_verifier,
        code_length: code?.length || 0
      }
    });

    // Validate grant type - support both authorization_code and token_exchange
    if (grant_type !== "authorization_code" && grant_type !== "urn:ietf:params:oauth:grant-type:token-exchange") {
      return NextResponse.json(
        {
          error: "unsupported_grant_type",
          error_description: "Only authorization_code and token_exchange grant types are supported"
        },
        { 
          status: 400,
          headers: {
            "Cache-Control": "no-store",
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
          }
        }
      );
    }
    
    // Handle token exchange flow (RFC 8693)
    if (grant_type === "urn:ietf:params:oauth:grant-type:token-exchange") {
      return handleTokenExchange(subject_token, subject_token_type, requested_token_type);
    }

    // Validate required parameters
    if (!code) {
      return NextResponse.json(
        {
          error: "invalid_request",
          error_description: "code parameter is required"
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

    if (!client_id) {
      return NextResponse.json(
        {
          error: "invalid_request", 
          error_description: "client_id parameter is required"
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

    // Parse authorization code
    let authData;
    try {
      const parts = code.split('.');
      if (parts.length !== 2) {
        throw new Error("Invalid code format");
      }
      
      const encodedData = parts[1];
      const decodedData = Buffer.from(encodedData, 'base64url').toString();
      authData = JSON.parse(decodedData);
      
      // Check if code has expired
      if (Date.now() > authData.expires_at) {
        return NextResponse.json(
          {
            error: "invalid_grant",
            error_description: "Authorization code has expired"
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

      // Validate client_id matches
      if (authData.client_id !== client_id) {
        return NextResponse.json(
          {
            error: "invalid_grant",
            error_description: "client_id does not match authorization request"
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

      // Validate redirect_uri matches (if provided)
      if (redirect_uri && authData.redirect_uri !== redirect_uri) {
        return NextResponse.json(
          {
            error: "invalid_grant",
            error_description: "redirect_uri does not match authorization request"
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

      // Validate PKCE if code_challenge was provided
      if (authData.code_challenge && !code_verifier) {
        return NextResponse.json(
          {
            error: "invalid_request",
            error_description: "code_verifier is required for PKCE"
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

      if (authData.code_challenge && code_verifier) {
        // Verify PKCE code challenge
        const hash = createHash('sha256').update(code_verifier).digest();
        const challenge = hash.toString('base64url');
        
        if (challenge !== authData.code_challenge) {
          return NextResponse.json(
            {
              error: "invalid_grant",
              error_description: "Invalid code_verifier"
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
      }

    } catch (error) {
      console.error("Error parsing authorization code:", error);
      return NextResponse.json(
        {
          error: "invalid_grant",
          error_description: "Invalid authorization code"
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

    // Extract Supabase JWT token from auth data
    const supabaseAccessToken = authData.supabase_access_token;
    
    if (!supabaseAccessToken) {
      Sentry.captureMessage('OAuth Token Exchange: No Supabase session found', {
        level: 'error',
        tags: { context: 'token_exchange' },
        extra: { 
          client_id,
          user_id: authData.user_id,
          user_email: authData.user_email,
          auth_data_keys: Object.keys(authData)
        }
      });
      
      return NextResponse.json(
        {
          error: "invalid_grant",
          error_description: "No valid Supabase session found for this authorization code"
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
    
    // Mint MCP access token
    const mcpAccessToken = await mintMCPAccessToken(
      authData.user_id,
      authData.user_email,
      supabaseAccessToken,
      authData.scope || "mcp:read mcp:write"
    );
    
    const expires_in = 3600; // 1 hour
    const token_type = "Bearer";
    const scope = authData.scope || "mcp:read mcp:write";

    // Return MCP access token
    const response = {
      access_token: mcpAccessToken,
      token_type,
      expires_in,
      scope,
      user_id: authData.user_id,
      user_email: authData.user_email,
    };

    // Add Sentry breadcrumb for successful token exchange
    Sentry.addBreadcrumb({
      message: 'OAuth Token Exchange: Successful token generation',
      category: 'auth.token',
      level: 'info',
      data: {
        client_id,
        scope,
        expires_in,
        user_id: authData.user_id,
        user_email: authData.user_email,
        token_length: mcpAccessToken.length
      }
    });

    return NextResponse.json(response, {
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      }
    });

  } catch (error) {
    console.error("Token endpoint error:", error);
    
    Sentry.captureException(error, {
      tags: { context: 'oauth_token_exchange' },
      extra: {
        hasRequestBody: !!request.body,
        contentType: request.headers.get('content-type')
      }
    });
    
    return NextResponse.json(
      {
        error: "server_error",
        error_description: "Internal server error"
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

/**
 * Handle token exchange flow (RFC 8693)
 */
async function handleTokenExchange(
  subject_token?: string,
  subject_token_type?: string,
  requested_token_type?: string
) {
  // Validate token exchange parameters
  if (!subject_token) {
    return NextResponse.json(
      {
        error: "invalid_request",
        error_description: "subject_token is required for token exchange"
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

  if (subject_token_type !== "urn:ietf:params:oauth:token-type:access_token") {
    return NextResponse.json(
      {
        error: "invalid_request",
        error_description: "subject_token_type must be urn:ietf:params:oauth:token-type:access_token"
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

  try {
    // Validate the Supabase JWT and extract user info
    const userInfo = await validateSupabaseJWT(subject_token);
    
    // Mint MCP access token
    const mcpAccessToken = await mintMCPAccessToken(
      userInfo.user_id,
      userInfo.email,
      subject_token,
      "mcp:read mcp:write"
    );
    
    const expires_in = 3600; // 1 hour
    const token_type = "Bearer";
    const scope = "mcp:read mcp:write";

    // Return MCP access token
    const response = {
      access_token: mcpAccessToken,
      token_type,
      expires_in,
      scope,
      issued_token_type: "urn:ietf:params:oauth:token-type:access_token",
    };

    Sentry.addBreadcrumb({
      message: 'Token Exchange: Successful MCP token generation',
      category: 'auth.token_exchange',
      level: 'info',
      data: {
        user_id: userInfo.user_id,
        email: userInfo.email,
        scope,
        expires_in,
        token_length: mcpAccessToken.length
      }
    });

    return NextResponse.json(response, {
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      }
    });

  } catch (error) {
    console.error("Token exchange error:", error);
    
    Sentry.captureException(error, {
      tags: { context: 'token_exchange' },
      extra: {
        subject_token_type,
        requested_token_type,
        has_subject_token: !!subject_token
      }
    });
    
    return NextResponse.json(
      {
        error: "invalid_grant",
        error_description: "Invalid or expired subject token"
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
}

/**
 * Validate Supabase JWT and extract user information
 */
async function validateSupabaseJWT(token: string) {
  // Use internal Supabase URL for server-side operations, fallback to public URL
  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  
  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Supabase configuration missing");
  }
  
  const response = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'apikey': supabaseAnonKey,
      'Content-Type': 'application/json'
    }
  });
  
  if (!response.ok) {
    throw new Error(`Supabase validation failed: ${response.status}`);
  }
  
  const userData = await response.json();
  
  return {
    user_id: userData.id,
    email: userData.email,
  };
}

/**
 * Mint MCP access token
 */
async function mintMCPAccessToken(
  userId: string,
  email: string,
  supabaseJWT: string,
  scope: string
): Promise<string> {
  const signingSecret = process.env.MCP_TOKEN_SIGNING_SECRET;
  
  if (!signingSecret) {
    throw new Error("MCP token signing secret not configured");
  }
  
  const frontendBaseUrl = process.env.NEXT_PUBLIC_FRONTEND_BASE_URL || 
                          process.env.FRONTEND_BASE_URL || 
                          'http://localhost:3000';
  
  const currentTime = Math.floor(Date.now() / 1000);
  const expiresIn = 3600; // 1 hour
  
  const claims = {
    iss: frontendBaseUrl,
    aud: "mcp",
    sub: userId,
    email: email,
    scope: scope,
    iat: currentTime,
    exp: currentTime + expiresIn,
    sb_at: supabaseJWT, // Supabase access token for downstream calls
  };
  
  return jwt.sign(claims, signingSecret, { algorithm: 'HS256' });
}

// Handle unsupported methods
export async function GET() {
  return NextResponse.json(
    {
      error: "invalid_request",
      error_description: "GET method not supported for token endpoint"
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
