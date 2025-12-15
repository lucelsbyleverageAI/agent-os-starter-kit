"""Async client for Tavily API used by Tavily tools.

Implements endpoints and headers mirroring the official Tavily MCP server logic.
"""

from typing import Any, Dict, Optional

import httpx

from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError
from ...config import settings
import os
from dotenv import load_dotenv


logger = get_logger(__name__)

load_dotenv()


class TavilyClient:
    """Lightweight async client for Tavily API."""

    BASE_URLS = {
        "search": "https://api.tavily.com/search",
        "extract": "https://api.tavily.com/extract",
        "crawl": "https://api.tavily.com/crawl",
        "map": "https://api.tavily.com/map",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        # Prefer explicit arg, then settings attribute if present, then environment variable
        self.api_key = (
            api_key
            or getattr(settings, "tavily_api_key", None)
            or os.getenv("TAVILY_API_KEY")
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "X-Client-Source": "MCP",
            }
            self._client = httpx.AsyncClient(headers=headers, timeout=30)
        return self._client

    def _require_key(self) -> None:
        if not self.api_key:
            raise ToolExecutionError("tavily", "TAVILY_API_KEY environment variable is required")

    def _filter_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out None, empty strings, empty lists, and False booleans from payload."""
        return {
            k: v for k, v in payload.items()
            if v is not None and v != "" and v != [] and v is not False
        }

    async def search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_key()
        client = await self._get_client()
        try:
            data = self._filter_payload(payload)
            data["api_key"] = self.api_key
            # Debug log the payload being sent (excluding api_key)
            debug_data = {k: v for k, v in data.items() if k != "api_key"}
            logger.info(f"Tavily search payload: {debug_data}")
            resp = await client.post(self.BASE_URLS["search"], json=data)
            if resp.status_code == 401:
                raise ToolExecutionError("tavily-search", "Invalid API key")
            if resp.status_code == 429:
                raise ToolExecutionError("tavily-search", "Usage limit exceeded")
            if resp.status_code == 400:
                # Log the actual error from Tavily
                try:
                    error_body = resp.json()
                    error_msg = error_body.get("detail", {}).get("error", resp.text)
                    logger.error(f"Tavily 400 error: {error_msg}")
                    raise ToolExecutionError("tavily-search", f"Tavily rejected request: {error_msg}")
                except Exception:
                    logger.error(f"Tavily 400 error (raw): {resp.text}")
                    raise ToolExecutionError("tavily-search", f"Tavily rejected request: {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("tavily-search", f"Tavily API error: {str(e)}")

    async def extract(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_key()
        client = await self._get_client()
        try:
            data = self._filter_payload(payload)
            data["api_key"] = self.api_key
            resp = await client.post(self.BASE_URLS["extract"], json=data)
            if resp.status_code == 401:
                raise ToolExecutionError("tavily-extract", "Invalid API key")
            if resp.status_code == 429:
                raise ToolExecutionError("tavily-extract", "Usage limit exceeded")
            resp.raise_for_status()
            return resp.json()
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("tavily-extract", f"Tavily API error: {str(e)}")

    async def crawl(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_key()
        client = await self._get_client()
        try:
            data = self._filter_payload(payload)
            data["api_key"] = self.api_key
            resp = await client.post(self.BASE_URLS["crawl"], json=data)
            if resp.status_code == 401:
                raise ToolExecutionError("tavily-crawl", "Invalid API key")
            if resp.status_code == 429:
                raise ToolExecutionError("tavily-crawl", "Usage limit exceeded")
            resp.raise_for_status()
            return resp.json()
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("tavily-crawl", f"Tavily API error: {str(e)}")

    async def map(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_key()
        client = await self._get_client()
        try:
            data = self._filter_payload(payload)
            data["api_key"] = self.api_key
            resp = await client.post(self.BASE_URLS["map"], json=data)
            if resp.status_code == 401:
                raise ToolExecutionError("tavily-map", "Invalid API key")
            if resp.status_code == 429:
                raise ToolExecutionError("tavily-map", "Usage limit exceeded")
            resp.raise_for_status()
            return resp.json()
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("tavily-map", f"Tavily API error: {str(e)}")

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


