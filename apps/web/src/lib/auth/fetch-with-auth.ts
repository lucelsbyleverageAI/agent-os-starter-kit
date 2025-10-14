import { Session } from "./types";
import { getSupabaseClient } from "./supabase-client";

/**
 * Fetch wrapper that handles token refresh automatically on 401/403 errors.
 *
 * This solves the race condition where Supabase refreshes tokens in the background,
 * invalidating the old token before the new one propagates to React state.
 *
 * Also proactively refreshes tokens that are about to expire to prevent 401 errors.
 *
 * @param url - The URL to fetch
 * @param options - Fetch options (headers, method, body, etc.)
 * @param session - Current session from Auth context
 * @returns Response from the fetch request
 */
export async function fetchWithAuth(
  url: string,
  options: RequestInit = {},
  session: Session | null
): Promise<Response> {
  if (!session?.accessToken) {
    // No session - make unauthenticated request
    return fetch(url, options);
  }

  // Check if token is expired or about to expire (within 60 seconds)
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = session.expiresAt || 0;
  const isExpiringSoon = expiresAt - now < 60;

  let currentToken = session.accessToken;

  // Proactively refresh if token is expiring soon
  if (isExpiringSoon) {
    try {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.refreshSession();

      if (!error && data.session?.access_token) {
        currentToken = data.session.access_token;
      }
    } catch (refreshError) {
      // If proactive refresh fails, continue with existing token
      console.warn("Proactive token refresh failed, using existing token:", refreshError);
    }
  }

  // First attempt with current token (or refreshed token if we just refreshed)
  let response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${currentToken}`,
    },
  });

  // If 401/403, the token might be stale due to background refresh
  // Get fresh token directly from Supabase client and retry ONCE
  if ((response.status === 401 || response.status === 403) && session) {
    try {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.refreshSession();

      if (!error && data.session?.access_token) {
        // IMPORTANT: Create a new fetch WITHOUT the original abort signal
        // The original signal may have been aborted by component cleanup
        const retryOptions = { ...options };

        // Remove the signal from retry to prevent abort interference
        delete retryOptions.signal;

        // Retry with the fresh token and new options
        response = await fetch(url, {
          ...retryOptions,
          headers: {
            ...retryOptions.headers,
            Authorization: `Bearer ${data.session.access_token}`,
          },
        });
      }
    } catch (refreshError) {
      // If refresh fails, return the original 401/403 response
      console.error("Token refresh failed during fetch retry:", refreshError);
    }
  }

  return response;
}
