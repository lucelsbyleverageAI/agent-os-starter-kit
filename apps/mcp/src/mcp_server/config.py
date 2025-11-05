"""Configuration management for the MCP server."""

import os
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=[".env.local", ".env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Arcade Configuration (Optional)
    enable_arcade: bool = Field(default=False, description="Enable Arcade tools integration")
    arcade_api_key: Optional[str] = Field(default=None, description="Arcade API key (required when enable_arcade=True)")
    arcade_base_url: str = Field(
        default="https://api.arcade.dev", description="Arcade API base URL"
    )

    # Tavily Configuration
    tavily_api_key: Optional[str] = Field(
        default=None, description="Tavily API key for web tools"
    )

    # E2B Code Sandbox Configuration
    e2b_api_key: Optional[str] = Field(
        default=None, description="E2B API key for code sandbox execution"
    )

    # MCP Server Configuration
    mcp_server_port: int = Field(default=8000, description="MCP server port")
    mcp_server_host: str = Field(default="0.0.0.0", description="MCP server host")
    mcp_log_level: str = Field(default="INFO", description="Log level")
    mcp_server_name: str = Field(
        default="custom-mcp-server", description="MCP server name"
    )

    # Authentication Configuration
    auth_provider: str = Field(default="supabase", description="Authentication provider")
    supabase_url: Optional[str] = Field(default=None, description="Supabase URL")
    supabase_anon_key: Optional[str] = Field(
        default=None, description="Supabase anonymous key"
    )
    supabase_service_key: Optional[str] = Field(
        default=None, description="Supabase service role key"
    )
    
    # OAuth 2.1 and MCP Authentication Configuration
    frontend_base_url: str = Field(
        default="http://localhost:3000", description="Frontend base URL for auth redirects"
    )
    mcp_public_base_url: Optional[str] = Field(
        default=None, description="Public base URL for MCP server (for external client discovery)"
    )
    langconnect_base_url: str = Field(
        default="http://langconnect:8080", description="LangConnect API base URL for internal communication"
    )
    oauth_issuer: Optional[str] = Field(
        default=None, description="OAuth 2.1 issuer URL (defaults to Supabase URL)"
    )
    oauth_audience: str = Field(
        default="authenticated", description="JWT audience for token validation"
    )
    enable_oauth_discovery: bool = Field(
        default=True, description="Enable OAuth 2.1 discovery endpoints"
    )
    
    # Service Account Configuration
    mcp_service_account_key: Optional[str] = Field(
        default=None, description="Service account key for LangGraph -> MCP authentication"
    )
    
    # MCP Token Configuration
    mcp_token_signing_secret: Optional[str] = Field(
        default=None, description="Secret for signing/validating MCP access tokens"
    )

    # Custom Tools Configuration
    enable_custom_tools: bool = Field(
        default=True, description="Enable custom tools"
    )
    custom_tools_config_path: str = Field(
        default="./config/custom_tools.json", description="Custom tools config path"
    )

    # Tool Filtering
    enabled_arcade_services: str = Field(
        default="gmail,google,gcal,microsoft,codesandbox,github,web,notiontoolkit,slack,math,hubspot,linkedin,dropbox,math,search",
        description="Comma-separated list of enabled Arcade services",
    )
    
    # Available toolkits from arcade can be found using poetry run python list_arcade_tools.py list-tools --summary-only
    # Available toolkits: asana,codesandbox,confluence,demo,dropbox,github,google,hubspot,jira,linkedin,math,microsoft,notiontoolkit,reddit,search,slack,spotify,stripe,web,x,zoom

    # Caching Configuration
    tool_cache_ttl: int = Field(
        default=3600, description="Tool cache TTL in seconds"
    )
    user_auth_cache_ttl: int = Field(
        default=1800, description="User auth cache TTL in seconds"
    )

    # Tool Execution Configuration
    tool_execution_timeout: int = Field(
        default=300, description="Tool execution timeout in seconds (5 minutes)"
    )

    # Development/Debug
    debug: bool = Field(default=False, description="Debug mode")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="CORS origins",
    )

    @property
    def enabled_services_list(self) -> List[str]:
        """Get enabled services as a list."""
        return [
            service.strip()
            for service in self.enabled_arcade_services.split(",")
            if service.strip()
        ]

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    def validate_required_settings(self) -> None:
        """Validate that required settings are present."""
        # Only validate Arcade settings if Arcade is enabled
        if self.enable_arcade and not self.arcade_api_key:
            raise ValueError("ARCADE_API_KEY is required when enable_arcade=True")

        if self.auth_provider == "supabase":
            if not self.supabase_url:
                raise ValueError("SUPABASE_URL is required when using Supabase auth")
            if not self.supabase_anon_key:
                raise ValueError(
                    "SUPABASE_ANON_KEY is required when using Supabase auth"
                )
        elif self.auth_provider == "none":
            # No validation needed for test/development mode
            pass


# Global settings instance
settings = Settings()

# Validate settings on import (skip in test environment)
import os
if not os.environ.get("PYTEST_CURRENT_TEST"):
    try:
        settings.validate_required_settings()
    except ValueError as e:
        # In development, just warn instead of failing
        if settings.debug:
            print(f"Warning: {e}")
        else:
            raise

# Export commonly used settings as module-level constants
LANGCONNECT_BASE_URL = settings.langconnect_base_url 