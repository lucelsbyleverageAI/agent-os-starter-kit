"""Arcade tools integration for the MCP server."""

import time
from typing import Dict, List, Optional

from ..config import settings
from ..utils.exceptions import ArcadeAPIError, ConfigurationError
from ..utils.logging import get_logger
from .base import ArcadeTool, BaseTool

logger = get_logger(__name__)


class ArcadeToolsManager:
    """Manages Arcade tools integration."""

    def __init__(self) -> None:
        self._tools_cache: Dict[str, ArcadeTool] = {}
        self._cache_timestamp: Optional[float] = None

        # Check if 'all' is specified to load all available tools
        enabled_services_list = settings.enabled_services_list
        self._load_all_services = 'all' in [s.lower() for s in enabled_services_list]
        self._enabled_services = set(enabled_services_list) if not self._load_all_services else set()

    async def get_available_tools(self, force_refresh: bool = False) -> List[BaseTool]:
        """Get available Arcade tools.
        
        Args:
            force_refresh: Force refresh of tools cache
            
        Returns:
            List of available Arcade tools
        """
        if self._should_refresh_cache() or force_refresh:
            await self._refresh_tools_cache()
        
        return list(self._tools_cache.values())

    async def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get a specific Arcade tool by name.
        
        Args:
            tool_name: The tool name (with or without 'arcade_' prefix)
            
        Returns:
            The tool if found, None otherwise
        """
        # Normalize tool name
        if not tool_name.startswith("arcade_"):
            tool_name = f"arcade_{tool_name}"
        
        # Ensure tools are loaded
        if self._should_refresh_cache():
            await self._refresh_tools_cache()
        
        return self._tools_cache.get(tool_name)

    def _should_refresh_cache(self) -> bool:
        """Check if tools cache should be refreshed."""
        if self._cache_timestamp is None:
            return True
        
        cache_age = time.time() - self._cache_timestamp
        return cache_age > settings.tool_cache_ttl

    async def _refresh_tools_cache(self) -> None:
        """Refresh the tools cache from Arcade API."""
        logger.info("Refreshing Arcade tools cache")

        try:
            # Lazy import arcade auth manager
            from ..auth.arcade_auth import arcade_auth_manager

            # Get all available tools from Arcade with pagination
            arcade_client = arcade_auth_manager.arcade_client
            all_tools = []
            offset = 0
            limit = 1000
            total_fetched = 0

            # Fetch all pages of tools
            while True:
                logger.debug(f"Fetching tools page with offset={offset}, limit={limit}")

                # Fetch the current page
                # Note: Using offset parameter if available, otherwise may need multiple calls
                if offset == 0:
                    response = arcade_client.tools.list(limit=limit)
                else:
                    # Try to use offset parameter if supported by the API
                    try:
                        response = arcade_client.tools.list(limit=limit, offset=offset)
                    except TypeError:
                        # If offset parameter is not supported, we can only get first batch
                        logger.warning("Arcade API client does not support offset parameter, fetching more tools via alternative method")
                        # Try alternative pagination if available
                        break

                if not response.items:
                    logger.debug(f"No more items at offset={offset}, stopping pagination")
                    break

                all_tools.extend(response.items)
                total_fetched += len(response.items)
                logger.debug(f"Fetched {len(response.items)} tools, total so far: {total_fetched}")

                # Check if we've fetched all available tools
                if len(response.items) < limit:
                    logger.debug(f"Fetched {len(response.items)} tools (less than limit {limit}), assuming end of data")
                    break

                # Move to next page
                offset += limit

                # Safety check to prevent infinite loops
                if offset > 10000:
                    logger.warning(f"Reached maximum offset {offset}, stopping pagination for safety")
                    break

            if not all_tools:
                logger.warning("No tools returned from Arcade API")
                return

            logger.info(f"Fetched {len(all_tools)} total tools from Arcade API")

            # Filter and create tool instances
            new_cache = {}
            filtered_count = 0

            for arcade_tool in all_tools:
                if self._should_include_tool(arcade_tool):
                    # Use the fully qualified name format: Toolkit_ToolName
                    if hasattr(arcade_tool, 'toolkit') and arcade_tool.toolkit:
                        toolkit_name = arcade_tool.toolkit.name
                        full_tool_name = f"{toolkit_name}_{arcade_tool.name}"
                    else:
                        # Fallback to just the tool name if no toolkit
                        full_tool_name = arcade_tool.name

                    tool_instance = ArcadeTool(
                        arcade_tool_name=full_tool_name,
                        arcade_definition=arcade_tool
                    )
                    new_cache[tool_instance.name] = tool_instance
                else:
                    filtered_count += 1

            self._tools_cache = new_cache
            self._cache_timestamp = time.time()

            logger.info(
                "Arcade tools cache refreshed",
                total_tools=len(all_tools),
                included_tools=len(new_cache),
                filtered_tools=filtered_count,
                load_all_services=self._load_all_services,
                enabled_services=list(self._enabled_services) if not self._load_all_services else "all"
            )
            
        except Exception as e:
            logger.error("Failed to refresh Arcade tools cache", error=str(e))
            raise ArcadeAPIError(f"Failed to refresh tools cache: {str(e)}")

    def _should_include_tool(self, arcade_tool) -> bool:
        """Check if a tool should be included based on configuration.

        Args:
            arcade_tool: The Arcade tool definition

        Returns:
            True if the tool should be included
        """
        # If loading all services, include all tools with a toolkit
        if self._load_all_services:
            if not hasattr(arcade_tool, 'toolkit') or not arcade_tool.toolkit:
                logger.debug("Skipping tool without toolkit", tool=arcade_tool.name)
                return False
            return True

        # Check if tool has a toolkit
        if not hasattr(arcade_tool, 'toolkit') or not arcade_tool.toolkit:
            logger.debug("Skipping tool without toolkit", tool=arcade_tool.name)
            return False

        toolkit_name = arcade_tool.toolkit.name.lower()

        # Check against enabled services
        if self._enabled_services and toolkit_name not in self._enabled_services:
            logger.debug(
                "Skipping tool from disabled service",
                tool=arcade_tool.name,
                toolkit=toolkit_name
            )
            return False

        # Additional filtering logic can be added here
        # For example, skip tools that require specific permissions

        return True

    def get_tools_by_service(self, service_name: str) -> List[BaseTool]:
        """Get tools for a specific service.
        
        Args:
            service_name: The service name (e.g., 'gmail', 'google')
            
        Returns:
            List of tools for the service
        """
        service_tools = []
        
        for tool in self._tools_cache.values():
            if hasattr(tool.arcade_definition, 'toolkit'):
                toolkit_name = tool.arcade_definition.toolkit.name.lower()
                if toolkit_name == service_name.lower():
                    service_tools.append(tool)
        
        return service_tools

    def get_available_services(self) -> List[str]:
        """Get list of available services.
        
        Returns:
            List of service names
        """
        services = set()
        
        for tool in self._tools_cache.values():
            if hasattr(tool.arcade_definition, 'toolkit'):
                services.add(tool.arcade_definition.toolkit.name.lower())
        
        return sorted(list(services))

    async def check_tool_authorization(self, user_id: str, tool_name: str) -> Optional[str]:
        """Check if user is authorized for a tool.
        
        Args:
            user_id: The user ID
            tool_name: The tool name
            
        Returns:
            Authorization URL if needed, None if authorized
        """
        # Lazy import arcade auth manager
        from ..auth.arcade_auth import arcade_auth_manager
        
        # Get the actual Arcade tool name
        tool = await self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        return arcade_auth_manager.check_user_authorization(
            user_id=user_id,
            tool_name=tool.arcade_tool_name
        )

    def invalidate_cache(self) -> None:
        """Invalidate the tools cache."""
        self._tools_cache.clear()
        self._cache_timestamp = None
        logger.info("Arcade tools cache invalidated")

    def update_enabled_services(self, services: List[str]) -> None:
        """Update enabled services and invalidate cache.

        Args:
            services: List of service names to enable
        """
        # Check if 'all' is specified
        self._load_all_services = 'all' in [s.lower() for s in services]
        self._enabled_services = set(service.lower() for service in services) if not self._load_all_services else set()
        self.invalidate_cache()
        logger.info(
            "Updated enabled services",
            load_all_services=self._load_all_services,
            services=list(self._enabled_services) if not self._load_all_services else "all"
        )


# Global Arcade tools manager instance
arcade_tools_manager = ArcadeToolsManager() 