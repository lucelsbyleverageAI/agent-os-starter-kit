import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/auth/supabase-client";

export async function GET(request: NextRequest) {
  try {
    // Parse the URL and get the code parameter
    const requestUrl = new URL(request.url);
    const code = requestUrl.searchParams.get("code");

    // Get the redirect destination (or default to home)
    const redirectTo = requestUrl.searchParams.get("redirect") || "/";

    if (code) {
      // Get Supabase client
      const supabase = getSupabaseClient();

      // Exchange the code for a session
      const { error } = await supabase.auth.exchangeCodeForSession(code);

      if (error) {
        console.error("Error exchanging code for session:", error);
        throw error;
      }

      // Successfully authenticated
    }

    // Check if this is part of an OAuth flow by looking for OAuth parameters in the redirect URL
    let isOAuthFlow = false;
    let oauthParams = new URLSearchParams();
    
    if (redirectTo.includes('response_type=') && redirectTo.includes('client_id=') && redirectTo.includes('redirect_uri=')) {
      isOAuthFlow = true;
      
      // Extract OAuth parameters from the redirect URL
      if (redirectTo.includes('?')) {
        // Handle both /auth/mcp-authorize?params and /?params formats
        const queryString = redirectTo.split('?')[1];
        oauthParams = new URLSearchParams(queryString);
      }
      
    }

    if (isOAuthFlow) {
      // This is an OAuth flow - redirect to the authorization endpoint instead of home
      const oauthAuthUrl = new URL('/auth/mcp-authorize', request.url);
      oauthAuthUrl.search = oauthParams.toString();
      
      return NextResponse.redirect(oauthAuthUrl);
    }

    // Redirect to the requested page or home
    return NextResponse.redirect(new URL(redirectTo, request.url));
  } catch (error) {
    console.error("Auth callback error:", error);

    // In case of error, redirect to sign-in with error message
    const errorUrl = new URL("/signin", request.url);
    errorUrl.searchParams.set(
      "error",
      "Authentication failed. Please try again.",
    );

    return NextResponse.redirect(errorUrl);
  }
}
