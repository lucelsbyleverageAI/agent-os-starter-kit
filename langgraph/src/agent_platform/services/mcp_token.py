"""
MCP token management for LangGraph agents.

New model:
- Exchange Supabase JWT for MCP access token when available
- Fall back to service account key when no user context

Uses token exchange (RFC 8693) to convert Supabase JWTs to MCP access tokens.
"""

import os
import aiohttp
from typing import Dict, Optional, Any
from langchain_core.runnables import RunnableConfig
from agent_platform.sentry import get_logger

MCP_SERVICE_ACCOUNT_KEY = os.environ.get("MCP_SERVICE_ACCOUNT_KEY")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")

logger = get_logger(__name__)


async def fetch_tokens(config: RunnableConfig) -> Optional[Dict[str, Any]]:
    """
    Exchange Supabase JWT for MCP access token or use service account key.
    
    Returns:
    - If Supabase JWT available: {"auth_type": "mcp_access_token", "access_token": <mcp_token>}
    - If only service account: {"auth_type": "service_account", "access_token": <key>}
    - None if no auth available
    """
    # Try multiple locations for Supabase token (for compatibility)
    supabase_token = (
        config.get("configurable", {}).get("x-supabase-access-token") or
        config.get("metadata", {}).get("supabaseAccessToken") or
        config.get("configurable", {}).get("supabaseAccessToken") or
        config.get("metadata", {}).get("headers", {}).get("x-supabase-access-token")
    )
    
    if supabase_token:
        # Exchange Supabase JWT for MCP access token
        logger.debug("[MCP_TOKEN] exchanging_supabase_jwt_for_mcp_token=true")
        try:
            mcp_token = await exchange_supabase_jwt_for_mcp_token(supabase_token)
            return {
                "auth_type": "mcp_access_token",
                "access_token": mcp_token
            }
        except Exception as e:
            logger.error(f"[MCP_TOKEN] token_exchange_failed error={str(e)}")
            # Fall through to service account if exchange fails
    
    # No user context - use service account if available
    if MCP_SERVICE_ACCOUNT_KEY:
        logger.debug("[MCP_TOKEN] using_service_account=true")
        user_id = config.get("metadata", {}).get("owner")
        return {
            "auth_type": "service_account",
            "access_token": MCP_SERVICE_ACCOUNT_KEY,
            "user_id": user_id
        }
    
    logger.warning("[MCP_TOKEN] no_auth_available=true")
    return None


async def exchange_supabase_jwt_for_mcp_token(supabase_jwt: str) -> str:
    """
    Exchange a Supabase JWT for an MCP access token using token exchange (RFC 8693).
    
    Args:
        supabase_jwt: Valid Supabase JWT
        
    Returns:
        str: MCP access token
        
    Raises:
        Exception: If token exchange fails
    """
    token_endpoint = f"{FRONTEND_BASE_URL}/auth/mcp-token"
    
    # Prepare token exchange request (RFC 8693)
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": supabase_jwt,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
    }
    
    logger.debug("[MCP_TOKEN] requesting_token_exchange endpoint=%s", token_endpoint)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            token_endpoint,
            data=data,  # Form data
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(
                    f"[MCP_TOKEN] token_exchange_failed status={response.status} error={error_text[:200]}"
                )
                raise Exception(f"Token exchange failed: {response.status} - {error_text}")
            
            result = await response.json()
            mcp_access_token = result.get("access_token")
            
            if not mcp_access_token:
                logger.error(f"[MCP_TOKEN] no_access_token_in_response keys={list(result.keys())}")
                raise Exception("No access token in exchange response")
            
            logger.debug(
                "[MCP_TOKEN] token_exchange_successful token_length=%d",
                len(mcp_access_token)
            )
            
            return mcp_access_token