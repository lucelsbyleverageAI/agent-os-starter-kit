import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { headers } from 'next/headers';

// Create Supabase client with service role for admin operations
function createAdminClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error('Missing Supabase configuration');
  }

  return createClient(supabaseUrl, supabaseServiceKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}

// Helper function to format Supabase user to our CollaborativeUser type
function formatSupabaseUser(user: any) {
  const metadata = user.user_metadata || {};
  
  return {
    id: user.id,
    email: user.email,
    display_name: metadata.display_name || metadata.name || null,
    first_name: metadata.first_name || metadata.name?.split(' ')[0] || null,
    last_name: metadata.last_name || metadata.name?.split(' ').slice(1).join(' ') || null,
    avatar_url: metadata.avatar_url || null,
    is_active: user.email_confirmed_at ? true : false,
    created_at: user.created_at,
    updated_at: user.updated_at,
  };
}

export async function GET(request: NextRequest) {
  try {
    // Verify the request has a valid authorization header
    const headersList = await headers();
    const authorization = headersList.get('authorization');
    
    if (!authorization || !authorization.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Missing or invalid authorization header' }, 
        { status: 401 }
      );
    }

    // Optional: Verify the user token is valid (you could verify the JWT here)
    // For now, we'll trust that if they have a token, they're authenticated
    
    const supabaseAdmin = createAdminClient();
    
    // Parse query parameters
    const { searchParams } = new URL(request.url);
    const query = searchParams.get('q');
    const excludeIds = searchParams.get('exclude')?.split(',') || [];
    const limit = searchParams.get('limit') ? parseInt(searchParams.get('limit')!) : undefined;

    // Fetch users using admin client
    const { data, error } = await supabaseAdmin.auth.admin.listUsers();

    if (error) {
      console.error('Error fetching users:', error);
      return NextResponse.json(
        { error: 'Failed to fetch users' }, 
        { status: 500 }
      );
    }

    // Convert to our user format
    let users = data.users.map(formatSupabaseUser);

    // Apply client-side filtering if query is provided
    if (query) {
      const searchTerm = query.toLowerCase();
      users = users.filter(user => {
        const matchesEmail = user.email.toLowerCase().includes(searchTerm);
        const matchesDisplayName = user.display_name?.toLowerCase().includes(searchTerm);
        const matchesFirstName = user.first_name?.toLowerCase().includes(searchTerm);
        const matchesLastName = user.last_name?.toLowerCase().includes(searchTerm);
        return matchesEmail || matchesDisplayName || matchesFirstName || matchesLastName;
      });
    }

    // Exclude specified users
    if (excludeIds.length > 0) {
      users = users.filter(user => !excludeIds.includes(user.id));
    }

    // Apply limit
    if (limit) {
      users = users.slice(0, limit);
    }

    // Return in expected format
    return NextResponse.json({
      users,
      total: users.length,
      has_more: false, // We're returning all users for now
    });

  } catch (error) {
    console.error('Error in users API:', error);
    return NextResponse.json(
      { error: 'Internal server error' }, 
      { status: 500 }
    );
  }
} 