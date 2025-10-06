import { Session } from "./types";
import { getSupabaseClient } from "./supabase-client";

/**
 * Fetch wrapper that handles token refresh automatically on 401/403 errors.
 *
 * This solves the race condition where Supabase refreshes tokens in the background,
 * invalidating the old token before the new one propagates to React state.
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

  // First attempt with current token from React state
  let response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${session.accessToken}`,
    },
  });

  // If 401/403, the token might be stale due to background refresh
  // Get fresh token directly from Supabase client and retry ONCE
  if ((response.status === 401 || response.status === 403) && session) {
    try {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.refreshSession();

      if (!error && data.session?.access_token) {
        // Retry with the fresh token
        response = await fetch(url, {
          ...options,
          headers: {
            ...options.headers,
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
