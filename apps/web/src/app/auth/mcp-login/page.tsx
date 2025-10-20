'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { createBrowserClient } from '@supabase/ssr';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2 } from 'lucide-react';
import * as Sentry from '@sentry/nextjs';

export default function MCPLoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );

  // OAuth parameters from the authorization request
  const clientId = searchParams.get('client_id');
  const clientName = searchParams.get('client_name') || 'MCP Client';
  const redirectUri = searchParams.get('redirect_uri');
  const scope = searchParams.get('scope');
  const state = searchParams.get('state');
  const codeChallenge = searchParams.get('code_challenge');
  const codeChallengeMethod = searchParams.get('code_challenge_method');
  const resource = searchParams.get('resource');

  const redirectToAuthorization = async () => {
    if (!clientId || !redirectUri) {
      const errorMsg = 'Invalid OAuth request parameters';
      Sentry.captureMessage(errorMsg, {
        level: 'error',
        tags: { context: 'mcp_oauth_redirect' },
        extra: { clientId, redirectUri }
      });
      setError(errorMsg);
      return;
    }

    // Redirect back to the authorization endpoint with all the original parameters
    const authParams = new URLSearchParams({
      response_type: 'code',
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: scope || 'openid email profile',
      ...(state && { state }),
      ...(codeChallenge && { code_challenge: codeChallenge }),
      ...(codeChallengeMethod && { code_challenge_method: codeChallengeMethod }),
      ...(resource && { resource }),
    });

    const authUrl = `/auth/mcp-authorize?${authParams.toString()}`;
    
    Sentry.addBreadcrumb({
      message: 'MCP Login: Redirecting to OAuth authorization endpoint',
      category: 'auth.mcp',
      level: 'info',
      data: { 
        authUrl, 
        clientId, 
        redirectUri,
        hasState: !!state,
        hasCodeChallenge: !!codeChallenge
      }
    });
    
    router.push(authUrl);
  };

  useEffect(() => {
    // Check if user is already logged in
    const checkSession = async () => {
      try {
        Sentry.addBreadcrumb({
          message: 'MCP Login: Checking existing session',
          category: 'auth.mcp',
          level: 'info',
          data: { clientId, redirectUri }
        });

        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          Sentry.addBreadcrumb({
            message: 'MCP Login: User already authenticated, redirecting to OAuth flow',
            category: 'auth.mcp',
            level: 'info',
            data: { userId: session.user?.id }
          });
          // User is already logged in, redirect back to authorization endpoint
          await redirectToAuthorization();
        } else {
          Sentry.addBreadcrumb({
            message: 'MCP Login: No existing session found, showing login form',
            category: 'auth.mcp',
            level: 'info'
          });
        }
      } catch (error) {
        Sentry.captureException(error, {
          tags: { context: 'mcp_login_session_check' },
          extra: { clientId, redirectUri }
        });
        console.error('Error checking session:', error);
      } finally {
        setIsCheckingSession(false);
      }
    };

    checkSession();
  }, [clientId, redirectUri, redirectToAuthorization, supabase.auth]);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      Sentry.addBreadcrumb({
        message: 'MCP Login: Starting sign-in process',
        category: 'auth.mcp',
        level: 'info',
        data: { email, clientId, redirectUri }
      });

      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        Sentry.captureException(error, {
          tags: { context: 'mcp_login_signin' },
          extra: { email, clientId, redirectUri }
        });
        throw error;
      }

      if (data.session) {
        Sentry.addBreadcrumb({
          message: 'MCP Login: Sign-in successful, redirecting directly to OAuth flow',
          category: 'auth.mcp',
          level: 'info',
          data: { 
            userId: data.session.user?.id,
            clientId, 
            redirectUri 
          }
        });

        // 🔧 CRITICAL FIX: Redirect directly to OAuth authorization endpoint
        // instead of going through Supabase's auth callback which ignores redirect parameter
        await redirectToAuthorization();
        return;
      }
    } catch (error: any) {
      Sentry.captureException(error, {
        tags: { context: 'mcp_login_signin_error' },
        extra: { email, clientId, redirectUri }
      });
      setError(error.message || 'Failed to sign in');
    } finally {
      setIsLoading(false);
    }
  };

  if (isCheckingSession) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="w-[400px]">
          <CardContent className="pt-6">
            <div className="flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2">Checking authentication...</span>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Card className="w-[400px]">
        <CardHeader>
          <CardTitle>Authorize MCP Access</CardTitle>
          <CardDescription>
            {clientName} is requesting access to your MCP tools.
            Please sign in to continue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSignIn} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  'Sign In'
                )}
              </Button>
            </div>
          </form>
          
          <div className="mt-4 p-4 bg-gray-50 rounded-lg">
            <h4 className="font-medium text-sm mb-2">Requested Permissions:</h4>
            <ul className="text-sm text-gray-600 space-y-1">
              <li>• Access to your profile information</li>
              <li>• Access to your MCP tools</li>
              <li>• Read your email address</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}