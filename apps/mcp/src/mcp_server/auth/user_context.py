"""User context management for MCP server authentication."""

import time
from typing import Any, Dict, Optional

from pydantic import BaseModel

from ..config import settings
from ..utils.exceptions import AuthenticationError
from ..sentry import get_logger
from .token_utils import (
    validate_mcp_access_token,
    extract_supabase_jwt_from_mcp_token,
    MCPTokenExpiredError,
    MCPTokenInvalidError,
)

logger = get_logger(__name__)


class UserContext(BaseModel):
    """User context information."""

    user_id: str
    email: Optional[str] = None
    metadata: Dict[str, Any] = {}
    authenticated_at: float
    expires_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        """Check if the user context has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if the user context is valid."""
        return not self.is_expired


class UserContextManager:
    """Manages user context and authentication."""

    def __init__(self) -> None:
        self._context_cache: Dict[str, UserContext] = {}

    def extract_user_context(self, headers: Dict[str, str]) -> UserContext:
        """Extract user context from request headers.
        
        Only accepts:
        - Authorization: Bearer <mcp_access_token> (preferred)
        - Authorization: Bearer <service_account_key> (for automation)
        """
        # Check standard Authorization header
        auth_header = headers.get("authorization") or headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer ") or auth_header == "Bearer":
            self._raise_auth_required_error()

        token = auth_header[7:]

        # Service account authentication (exact match)
        if settings.mcp_service_account_key and token == settings.mcp_service_account_key:
            logger.info("Service account authentication successful")
            return self._create_service_account_context()

        # MCP access token validation
        user_context = self._validate_mcp_access_token(token)
        logger.info("MCP token authentication successful", user_id=user_context.user_id)
        return user_context

    def _validate_mcp_access_token(self, token: str) -> UserContext:
        """Validate MCP access token and extract user context."""
        try:
            # Validate the MCP token
            claims = validate_mcp_access_token(token)
            
            # Extract user information from claims
            user_id = claims.get("sub")
            email = claims.get("email")
            scope = claims.get("scope", "")
            supabase_jwt = claims.get("sb_at")  # Supabase JWT for downstream calls
            
            if not user_id:
                raise AuthenticationError("Invalid MCP token: missing user ID")
            
            # Create user context
            current_time = time.time()
            user_context = UserContext(
                user_id=user_id,
                email=email,
                metadata={
                    "auth_method": "mcp_access_token",
                    "scope": scope,
                    "jwt_token": supabase_jwt,  # Store Supabase JWT for LangConnect calls
                    "token_exp": claims.get("exp"),
                },
                authenticated_at=current_time,
                expires_at=claims.get("exp", current_time + settings.user_auth_cache_ttl),
            )
            
            # Cache the validated context
            self._context_cache[user_id] = user_context
            
            logger.info(
                "MCP token validation successful",
                user_id=user_id,
                email=email,
                scope=scope,
                has_supabase_jwt=bool(supabase_jwt)
            )
            
            return user_context
            
        except MCPTokenExpiredError:
            logger.warning("MCP token expired")
            raise AuthenticationError("Token has expired")
            
        except MCPTokenInvalidError as e:
            logger.warning("Invalid MCP token", error=str(e))
            raise AuthenticationError(f"Invalid token: {str(e)}")
            
        except Exception as e:
            logger.error("Unexpected error during MCP token validation", error=str(e))
            raise AuthenticationError(f"Token validation failed: {str(e)}")

    def _raise_auth_required_error(self) -> None:
        """Raise authentication error with proper OAuth 2.1 context."""
        login_url = self._generate_login_url()
        
        # Create RFC 9728 compliant error with resource metadata
        base_url = settings.mcp_public_base_url or f"http://{settings.mcp_server_host}:{settings.mcp_server_port}"
        resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
        resource_uri = f"{base_url}/mcp"
        
        error_msg = "Authentication required. Use Authorization: Bearer <mcp_access_token> or service account key."
        if login_url:
            error_msg += f" For user authentication, visit: {login_url}"
        
        # Add context for proper WWW-Authenticate header construction
        auth_error = AuthenticationError(error_msg)
        auth_error.context = {
            "auth_url": login_url,
            "www_authenticate": f'Bearer realm="OAuth", resource_metadata="{resource_metadata_url}", resource="{resource_uri}"',
            "resource_metadata_url": resource_metadata_url,
            "resource_uri": resource_uri,
        }
        
        raise auth_error
    
    def _generate_login_url(self) -> Optional[str]:
        """Generate login URL for external clients."""
        if hasattr(settings, 'frontend_base_url') and settings.frontend_base_url:
            return f"{settings.frontend_base_url}/auth/mcp-login"
        
        return "http://localhost:3000/auth/mcp-login"

    def _create_service_account_context(self) -> UserContext:
        """Create user context for service account authentication.
        
        Service accounts:
        - Cannot access memory tools (no user JWT)
        - Used for automation and system tasks
        - Have admin access to non-user-specific tools
        """
        current_time = time.time()
        
        return UserContext(
            user_id="service_account",
            email=None,
            metadata={
                "auth_method": "service_account",
                "service_account": True,
                "admin_access": True,
                # No jwt_token - memory tools will be blocked
            },
            authenticated_at=current_time,
            expires_at=current_time + settings.user_auth_cache_ttl,
        )

    def invalidate_user_context(self, user_id: str) -> None:
        """Invalidate cached user context."""
        if user_id in self._context_cache:
            del self._context_cache[user_id]
            logger.info("Invalidated user context", user_id=user_id)

    def cleanup_expired_contexts(self) -> None:
        """Clean up expired user contexts from cache."""
        expired_users = [
            user_id for user_id, context in self._context_cache.items()
            if context.is_expired
        ]
        
        for user_id in expired_users:
            del self._context_cache[user_id]
        
        if expired_users:
            logger.info("Cleaned up expired contexts", count=len(expired_users))


# Global user context manager instance
user_context_manager = UserContextManager() 