"""
LangGraph Integration Service

This service handles communication with the LangGraph backend.
Provides core connection functionality and request handling for the Agent Access System V2.
"""

import os
import logging
from typing import Dict, Any, Optional
import httpx
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class LangGraphDeployment:
    """Configuration for a LangGraph deployment."""
    id: str
    url: str
    api_key: Optional[str] = None


class LangGraphService:
    """Service for integrating with LangGraph backend."""
    
    def __init__(self):
        """Initialize the LangGraph service with deployment configuration."""
        # Get LangGraph configuration from environment
        self.deployment_url = os.getenv("LANGCONNECT_LANGGRAPH_API_URL", "http://localhost:2024")
        self.api_key = os.getenv("LANGSMITH_API_KEY")
        
        if not self.deployment_url:
            log.warning("LANGGRAPH_API_URL not configured - LangGraph integration disabled")
        
        self.deployment = LangGraphDeployment(
            id="default",
            url=self.deployment_url,
            api_key=self.api_key
        )
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated request to LangGraph API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path (with or without leading slash)
            data: Request payload for POST/PUT requests
            headers: Additional headers to include
            
        Returns:
            JSON response from LangGraph API
            
        Raises:
            RuntimeError: If API request fails or configuration is invalid
        """
        if not self.deployment_url:
            raise RuntimeError("LangGraph API URL not configured")
        
        url = f"{self.deployment_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # Set up headers
        request_headers = {
            "Content-Type": "application/json",
        }

        # Prefer user token when provided; otherwise fall back to admin key
        if user_token:
            request_headers["Authorization"] = f"Bearer {user_token}"
            # Many LangGraph deployments expect the Supabase token in this header for user-scoped auth
            request_headers["x-supabase-access-token"] = user_token
        elif self.api_key:
            request_headers["x-auth-scheme"] = "langsmith"
            request_headers["x-api-key"] = self.api_key
        
        if headers:
            request_headers.update(headers)
        
        log.debug(f"Making {method} request to: {url}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    headers=request_headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                # Handle 204 No Content responses (common for DELETE operations)
                if response.status_code == 204:
                    return {"success": True}
                    
                # Handle responses with content
                try:
                    return response.json()
                except ValueError:
                    # If we can't parse JSON, return empty dict
                    log.warning(f"Could not parse JSON response from {url}, status: {response.status_code}")
                    return {"success": True}
                    
            except httpx.HTTPError as e:
                log.error(f"LangGraph API request failed: {e}")
                raise RuntimeError(f"LangGraph API request failed: {e}")

    async def delete_thread(self, thread_id: str, *, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Delete a thread by ID in the LangGraph backend."""
        return await self._make_request(
            method="DELETE",
            endpoint=f"/threads/{thread_id}",
            user_token=user_token,
        )

    async def search_threads(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search threads via LangGraph with optional filters (user-scoped)."""
        payload: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            payload["status"] = status
        if metadata:
            payload["metadata"] = metadata
        return await self._make_request(
            method="POST",
            endpoint="/threads/search",
            data=payload,
            user_token=user_token,
        )


def get_langgraph_service() -> LangGraphService:
    """Get the LangGraph service instance (dependency injection)."""
    return LangGraphService() 