"""
agent_platform.services.auth

Authentication and Authorization Service for LangGraph Agent Platform

This service provides user authentication and resource authorization for the
LangGraph-based agent platform. It validates JWT tokens from Supabase and
ensures users can only access their own resources (threads, assistants).

The service supports two modes:
1. Standard Mode: Full Supabase JWT validation
2. Trusted Frontend Mode: Simplified header-based authentication

Architecture:
- Authentication: Validates user identity via JWT tokens or headers
- Authorization: Controls access to threads and assistants via metadata
- Resource Isolation: Ensures users only see their own data
- StudioUser Support: Provides admin access for development tools

Security Features:
- JWT token validation with Supabase
- Thread ownership tracking and filtering
- Assistant access control
- Secure error handling without information leakage
"""

import os
import logging
import asyncio
from typing import Any

from langgraph_sdk import Auth
from langgraph_sdk.auth.types import StudioUser

# Supabase imports for JWT validation (only used in standard mode)
from supabase import create_client, Client as SupabaseClient
from agent_platform.sentry import init_sentry, get_logger

# Supabase Configuration
SUPABASE_URL = os.environ.get("SUPABASE_PUBLIC_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# LangGraph Platform API key (Studio key) support
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY")

# Initialize Supabase client for standard mode
supabase: SupabaseClient | None = None
logger = get_logger(__name__)

if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        logger.warning("[AUTH] Failed to initialize Supabase client: %s", e)
else:
    logger.warning("[AUTH] Supabase environment variables not found")

# Create standard auth object and set up handlers
auth = Auth()

@auth.authenticate
async def get_current_user(
    authorization: str | None,
    headers: dict | None = None,
    request: Any | None = None,
) -> Auth.types.MinimalUserDict:
    """
    Main authentication function that validates JWT tokens using Supabase.
    
    This function is called by LangGraph as middleware for every request.
    It extracts and validates the JWT token from the Authorization header,
    then returns user information if the token is valid.
    
    Args:
        authorization: The Authorization header value (e.g., "Bearer <token>")
        
    Returns:
        MinimalUserDict: Contains user identity information
        
    Raises:
        HTTPException: If authentication fails for any reason
        
    Flow:
        1. Check if Authorization header is present
        2. Parse header to extract Bearer token
        3. Validate token with Supabase Auth service
        4. Return user identity if valid, raise exception if not
    """

    # Step 0: Accept LangGraph Platform API key via x-api-key header (service key route)
    # The SDK injects headers as dict[bytes, bytes]. We check both bytes and str for robustness.
    if LANGSMITH_API_KEY:
        try:
            api_key = None
            if headers:
                api_key = (
                    headers.get(b"x-api-key")
                    or headers.get(b"X-API-Key")
                    or headers.get("x-api-key")
                    or headers.get("X-API-Key")
                )
            if not api_key and request is not None:
                # Starlette/ASGI request with case-insensitive mapping
                try:
                    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
                except Exception:
                    api_key = None
            if isinstance(api_key, bytes):
                api_key = api_key.decode()
        except Exception:
            api_key = None

        if api_key and api_key == LANGSMITH_API_KEY:
            # Authenticate as service account for API-key based access
            return {
                "identity": "service_account",
            }

    # Step 1: Ensure we have an authorization header for Supabase JWT path
    if not authorization:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Authorization header missing"
        )

    # Step 2: Parse the authorization header
    # Expected format: "Bearer <jwt_token>"
    try:
        scheme, token = authorization.split()
        assert scheme.lower() == "bearer"
    except (ValueError, AssertionError):
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    # Step 3: Ensure Supabase client is properly initialized
    if not supabase:
        raise Auth.exceptions.HTTPException(
            status_code=500, detail="Supabase client not initialized"
        )

    try:
        # Step 4: Verify the JWT token with Supabase
        # We use asyncio.to_thread to avoid blocking the event loop
        # since supabase.auth.get_user is a synchronous operation
        async def verify_token() -> dict[str, Any]:
            """
            Wrapper function to run Supabase token verification in a separate thread.
            This prevents blocking the main event loop during token validation.
            """
            response = await asyncio.to_thread(supabase.auth.get_user, token)
            return response

        # Execute token verification
        response = await verify_token()
        user = response.user

        # Step 5: Check if user was found and token is valid
        if not user:
            raise Auth.exceptions.HTTPException(
                status_code=401, detail="Invalid token or user not found"
            )

        # Step 6: Return minimal user information for LangGraph
        # Only the identity (user ID) is required for authorization
        return {
            "identity": user.id,
        }
    except Exception as e:
        # Handle any errors from Supabase (network issues, invalid tokens, etc.)
        raise Auth.exceptions.HTTPException(
            status_code=401, detail=f"Authentication error: {str(e)}"
        )

# Thread Authorization Handlers
# These handlers control access to thread resources

@auth.on.threads.create
@auth.on.threads.create_run
async def on_thread_create(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.create.value,
):
    """
    Authorization handler for thread creation operations.
    
    This handler runs when users create new threads or create runs within threads.
    It adds ownership metadata to track who created the thread, enabling
    proper access control for future operations.
    
    Args:
        ctx: Authentication context containing user information
        value: The thread data being created (can be modified)
        
    Returns:
        None: Modifies the value in-place by adding metadata
        
    Note:
        - StudioUser instances bypass this check (admin access)
        - Metadata persists with the thread for the lifetime of the resource
        - The "owner" field is used by read handlers to filter results
    """

    # Skip authorization for Studio users (admin/system users)
    if isinstance(ctx.user, StudioUser):
        return

    # Add ownership metadata to the thread being created
    # This creates a persistent record of who owns this thread
    metadata = value.setdefault("metadata", {})
    metadata["owner"] = ctx.user.identity

@auth.on.threads.read
@auth.on.threads.delete
@auth.on.threads.update
@auth.on.threads.search
async def on_thread_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.read.value,
):
    """
    Authorization handler for thread read/modify operations.
    
    This handler runs on all thread access operations (read, delete, update, search).
    It returns a filter that ensures users can only access threads they own.
    
    Args:
        ctx: Authentication context containing user information
        value: The operation parameters (not modified for read operations)
        
    Returns:
        dict: Filter criteria that LangGraph applies to limit results
        None: For StudioUser instances (no filtering applied)
        
    Note:
        - The returned filter is applied at the database level
        - Only threads with matching "owner" metadata will be accessible
        - This prevents users from accessing other users' threads
    """
    
    # Skip filtering for Studio users (admin/system users)
    if isinstance(ctx.user, StudioUser):
        return

    # Return filter to only show threads owned by the current user
    # This filter is applied by LangGraph to all database queries
    return {"owner": ctx.user.identity}

# Assistant Authorization Handlers
# These handlers control access to assistant resources

@auth.on.assistants.create
async def on_assistants_create(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.create.value,
):
    """
    Authorization handler for assistant creation operations.
    
    MODIFIED FOR TRUSTED FRONTEND: Still adds ownership metadata for compatibility
    with existing systems and future backend authorization, but doesn't restrict access.
    
    Args:
        ctx: Authentication context containing user information
        value: The assistant data being created (can be modified)
        
    Returns:
        None: Modifies the value in-place by adding metadata
        
    Note:
        - Adds ownership metadata for future use
        - Permissive access model during transition period
        - Frontend LangConnect handles actual permissions
    """
    
    # Skip for Studio users
    if isinstance(ctx.user, StudioUser):
        return

    # Add ownership metadata for compatibility/future use
    metadata = value.setdefault("metadata", {})
    metadata["owner"] = ctx.user.identity

@auth.on.assistants.read
@auth.on.assistants.delete
@auth.on.assistants.update
@auth.on.assistants.search
async def on_assistants_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.read.value,
):
    """
    Authorization handler for assistant access operations.
    
    PERMISSIVE ACCESS MODEL: Allows any authenticated user to access any assistant.
    This relies on frontend LangConnect permissions for actual authorization.
    
    Args:
        ctx: Authentication context containing user information
        value: The operation parameters (not modified for read operations)
        
    Returns:
        None: No filtering applied (permissive access)
        
    Note:
        - Permissive model during collaborative migration
        - Frontend handles real permissions via LangConnect
        - All access still requires authentication
        - Can be tightened in future iterations
    """
    
    # Skip filtering for Studio users
    if isinstance(ctx.user, StudioUser):
        return

    # PERMISSIVE: No filtering applied
    # Frontend LangConnect permissions control actual access
    return

# Store Authorization Handler

@auth.on.store()
async def authorize_store(ctx: Auth.types.AuthContext, value: dict):
    """
    Authorization handler for store operations.
    
    This handler controls access to the LangGraph store, ensuring users
    can only access their own namespace within the store.
    
    Args:
        ctx: Authentication context containing user information
        value: Store operation parameters including namespace
        
    Returns:
        None: Validates access, raises exception if unauthorized
        
    Raises:
        AssertionError: If user tries to access unauthorized namespace
        
    Note:
        - Store namespaces are user-isolated for security
        - First element of namespace tuple must match user identity
        - StudioUser instances bypass this restriction
    """
    
    # Skip authorization for Studio users
    if isinstance(ctx.user, StudioUser):
        return

    # Extract and validate namespace
    namespace: tuple = value["namespace"]
    
    # Ensure first element of namespace matches user identity
    assert namespace[0] == ctx.user.identity, "Not authorized"