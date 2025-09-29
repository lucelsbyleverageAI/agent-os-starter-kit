import type { NextRequest } from "next/server";
import { updateSession } from "./lib/auth/middleware";

export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  // Skip middleware for static assets and endpoints that handle auth
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - api/auth (auth API routes)
     */
    "/((?!_next/static|_next/image|favicon.ico|api/langconnect|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",

    /*
     * Match all API routes except for auth-related ones, email templates, and langconnect proxy
     * This allows the middleware to run on API routes and check authentication
     * but excludes email-templates which need to be publicly accessible for Supabase
     * and langconnect proxy which handles its own authentication
     */
    "/api/((?!auth|email-templates|langconnect).*)",
  ],
};
