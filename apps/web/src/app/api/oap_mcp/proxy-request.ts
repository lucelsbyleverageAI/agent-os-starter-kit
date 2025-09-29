import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

const MCP_SERVER_URL = process.env.NEXT_PUBLIC_MCP_SERVER_URL;

async function getSupabaseToken(req: NextRequest, debugId: string) {
  // Use PUBLIC Supabase URL/Anon key to ensure reachability from the server runtime
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    return null;
  }

  try {
    const supabase = createServerClient(supabaseUrl, supabaseKey, {
      cookies: {
        get(name: string) {
          return req.cookies.get(name)?.value;
        },
        set() {
          // No-op for this proxy route
        },
        remove() {
          // No-op for this proxy route
        },
      },
    });

    const { data: { session } } = await supabase.auth.getSession();
    const hasSession = !!session?.access_token;
    return hasSession ? session!.access_token! : null;
  } catch (error) {
    console.error("Error getting Supabase token:", error);
    return null;
  }
}

function normalizeBaseUrl(u: URL) {
  // Remove trailing slash from href to avoid double slashes
  const s = u.toString().replace(/\/$/, "");
  return s;
}

async function exchangeSupabaseForMcpToken(
  req: NextRequest,
  supabaseToken: string,
  debugId: string,
) {
  // Prepare candidate URLs (try internal first to avoid Caddy loopback issues)
  const candidates: URL[] = [];
  try { candidates.push(new URL("http://127.0.0.1:3000/auth/mcp-token")); } catch (_e) { void _e; }
  try { candidates.push(new URL("/auth/mcp-token", req.url)); } catch (_e) { void _e; }
  try {
    const baseApi = process.env.NEXT_PUBLIC_BASE_API_URL;
    if (baseApi) {
      const u = new URL(baseApi);
      // strip trailing /api if present
      const basePath = u.pathname.replace(/\/?api\/?$/, "/");
      u.pathname = `${basePath.replace(/\/$/, "")}/auth/mcp-token`;
      candidates.push(u);
    }
  } catch (_e) { void _e; }

  const form = new URLSearchParams();
  form.set("grant_type", "urn:ietf:params:oauth:grant-type:token-exchange");
  form.set("subject_token", supabaseToken);
  form.set(
    "subject_token_type",
    "urn:ietf:params:oauth:token-type:access_token",
  );
  form.set(
    "requested_token_type",
    "urn:ietf:params:oauth:token-type:access_token",
  );

  let lastErr: any = null;
  for (const tokenUrl of candidates) {
    try {
      const resp = await fetch(tokenUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });
      if (!resp.ok) {
        const _text = await resp.text().catch(() => "");
        lastErr = new Error(`MCP token exchange failed: ${resp.status} ${resp.statusText}`);
        continue;
      }
      const data = await resp.json();
      const accessToken = data?.access_token as string | undefined;
      if (!accessToken) {
        lastErr = new Error("MCP token exchange response missing access_token");
        continue;
      }
      return accessToken;
    } catch (e: any) {
      lastErr = e;
      continue;
    }
  }
  throw lastErr || new Error("MCP token exchange failed: no candidates succeeded");
}

/**
 * Proxies authenticated requests from frontend to MCP server.
 * SIMPLIFIED: Just uses the Supabase JWT directly - no token exchange needed!
 */
export async function proxyRequest(req: NextRequest): Promise<Response> {
  if (!MCP_SERVER_URL) {
    return new Response(
      JSON.stringify({
        message:
          "MCP_SERVER_URL environment variable is not set. Please set it to the URL of your MCP server, or NEXT_PUBLIC_MCP_SERVER_URL if you do not want to use the proxy route.",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  const url = new URL(req.url);
  const path = url.pathname.replace(/^\/api\/oap_mcp/, "");

  const targetUrlObj = new URL(MCP_SERVER_URL);
  // Normalize to avoid double slashes
  const targetBase = normalizeBaseUrl(targetUrlObj);
  const targetUrl = `${targetBase}/mcp${path}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers.append(key, value);
    }
  });

  let requestBody: any = null;
  let requestId: any = null;
  
  if (req.method !== "GET" && req.method !== "HEAD") {
    try {
      const bodyText = await req.text();
      if (bodyText) {
        requestBody = JSON.parse(bodyText);
        requestId = requestBody.id || null;
      }
    } catch (_e) {
      // If body parsing fails, continue without it
      void _e;
    }
  }

  // Require a Supabase session for all frontend requests
  const debugId = Math.random().toString(36).slice(2, 8);
  const supabaseToken = await getSupabaseToken(req, debugId);
  if (!supabaseToken) {
    return new Response(
      JSON.stringify({
        jsonrpc: "2.0",
        id: requestId,
        error: {
          code: -32001,
          message: "Authentication required - no valid Supabase session found.",
        },
      }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
  }

  // Exchange Supabase JWT for MCP access token and forward it
  let mcpAccessToken: string;
  try {
    mcpAccessToken = await exchangeSupabaseForMcpToken(req, supabaseToken, debugId);
  } catch (e: any) {
    return new Response(
      JSON.stringify({
        jsonrpc: "2.0",
        id: requestId,
        error: {
          code: -32001,
          message: "Authentication failed: unable to exchange token",
          data: { reason: e?.message || "exchange_failed" },
        },
      }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
  }

  headers.set("Authorization", `Bearer ${mcpAccessToken}`);
  headers.set("Accept", "application/json, text/event-stream");

  let body: BodyInit | null | undefined = undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    if (requestBody) {
      body = JSON.stringify(requestBody);
    } else {
      body = req.body;
    }
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000);

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.status === 204) {
      const newResponse = new Response(null, {
        status: 204,
        statusText: response.statusText,
      });
      response.headers.forEach((value, key) => {
        newResponse.headers.set(key, value);
      });
      return newResponse;
    }

    const responseClone = response.clone();
    let newResponse: NextResponse;

    try {
      const responseData = await responseClone.json();
      newResponse = NextResponse.json(responseData, {
        status: response.status,
        statusText: response.statusText,
      });
    } catch (_) {
      const responseBody = await response.text();
      newResponse = new NextResponse(responseBody, {
        status: response.status,
        statusText: response.statusText,
      });
    }

    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "content-length") {
        newResponse.headers.set(key, value);
      }
    });

    // No cookies needed - stateless bearer auth
    return newResponse;
  } catch (error) {
    console.error("MCP Proxy Error:", error);
    
    let errorMessage = "Unknown error";
    let statusCode = 502;
    
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        errorMessage = "Request timeout - the operation took too long to complete (>5 minutes)";
        statusCode = 504;
      } else {
        errorMessage = error.message;
      }
    }
    
    return new Response(
      JSON.stringify({ 
        jsonrpc: "2.0",
        id: requestId,
        error: {
          code: statusCode === 504 ? -32603 : -32002,
          message: statusCode === 504 ? errorMessage : "Proxy request failed",
          data: { originalError: errorMessage }
        }
      }),
      {
        status: statusCode,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}
