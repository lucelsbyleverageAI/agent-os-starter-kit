"""MCP access token utilities for minting and validating tokens."""

import time
import jwt
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from ..config import settings
from ..sentry import get_logger

logger = get_logger(__name__)


class MCPTokenError(Exception):
    """Base exception for MCP token operations."""
    pass


class MCPTokenExpiredError(MCPTokenError):
    """Token has expired."""
    pass


class MCPTokenInvalidError(MCPTokenError):
    """Token is invalid."""
    pass


def mint_mcp_access_token(
    user_id: str,
    email: str,
    supabase_jwt: str,
    scope: str = "mcp:read mcp:write",
    expires_in: int = 3600
) -> str:
    """
    Mint an MCP access token for a user.
    
    Args:
        user_id: User ID from Supabase
        email: User email
        supabase_jwt: Original Supabase JWT for downstream calls
        scope: Token scope (space-separated)
        expires_in: Token lifetime in seconds (default 1 hour)
        
    Returns:
        str: Signed MCP access token
        
    Raises:
        MCPTokenError: If token minting fails
    """
    if not settings.mcp_token_signing_secret:
        raise MCPTokenError("MCP token signing secret not configured")
    
    current_time = int(time.time())
    
    # Create JWT claims
    claims = {
        "iss": settings.frontend_base_url,  # Issuer is the frontend auth server
        "aud": "mcp",  # Audience is the MCP server
        "sub": user_id,  # Subject is the user ID
        "email": email,
        "scope": scope,
        "iat": current_time,
        "exp": current_time + expires_in,
        "sb_at": supabase_jwt,  # Private claim: Supabase access token for downstream calls
    }
    
    try:
        # Sign with HS256
        token = jwt.encode(
            claims,
            settings.mcp_token_signing_secret,
            algorithm="HS256"
        )
        
        logger.info(
            "Minted MCP access token",
            user_id=user_id,
            email=email,
            scope=scope,
            expires_in=expires_in,
            token_length=len(token)
        )
        
        return token
        
    except Exception as e:
        logger.error("Failed to mint MCP token", error=str(e), user_id=user_id)
        raise MCPTokenError(f"Failed to mint token: {str(e)}")


def validate_mcp_access_token(token: str) -> Dict[str, Any]:
    """
    Validate an MCP access token and return claims.
    
    Args:
        token: MCP access token to validate
        
    Returns:
        dict: Token claims if valid
        
    Raises:
        MCPTokenExpiredError: If token has expired
        MCPTokenInvalidError: If token is invalid
    """
    if not settings.mcp_token_signing_secret:
        raise MCPTokenInvalidError("MCP token signing secret not configured")
    
    try:
        # Decode and verify token
        claims = jwt.decode(
            token,
            settings.mcp_token_signing_secret,
            algorithms=["HS256"],
            audience="mcp",
            issuer=settings.frontend_base_url,
            options={"verify_exp": True}
        )
        
        logger.info(
            "Validated MCP access token",
            user_id=claims.get("sub"),
            email=claims.get("email"),
            scope=claims.get("scope"),
            token_length=len(token)
        )
        
        return claims
        
    except jwt.ExpiredSignatureError:
        logger.warning("MCP token expired", token_length=len(token))
        raise MCPTokenExpiredError("Token has expired")
        
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid MCP token", error=str(e), token_length=len(token))
        raise MCPTokenInvalidError(f"Invalid token: {str(e)}")
        
    except Exception as e:
        logger.error("Unexpected error validating MCP token", error=str(e))
        raise MCPTokenInvalidError(f"Token validation failed: {str(e)}")


def extract_supabase_jwt_from_mcp_token(token: str) -> Optional[str]:
    """
    Extract the Supabase JWT from an MCP access token for downstream calls.
    
    Args:
        token: MCP access token
        
    Returns:
        str: Supabase JWT if present, None otherwise
        
    Raises:
        MCPTokenInvalidError: If token is invalid
    """
    try:
        claims = validate_mcp_access_token(token)
        supabase_jwt = claims.get("sb_at")
        
        if supabase_jwt:
            logger.debug(
                "Extracted Supabase JWT from MCP token",
                user_id=claims.get("sub"),
                supabase_jwt_length=len(supabase_jwt)
            )
        
        return supabase_jwt
        
    except (MCPTokenExpiredError, MCPTokenInvalidError):
        raise
    except Exception as e:
        logger.error("Failed to extract Supabase JWT from MCP token", error=str(e))
        raise MCPTokenInvalidError(f"Failed to extract Supabase JWT: {str(e)}")
