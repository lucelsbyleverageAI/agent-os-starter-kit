"""Main entry point for the MCP server."""

import asyncio
import os
import sys
from typing import Optional
import time

import click

from .config import settings
from .server import create_server
from .sentry import init_sentry, get_logger

# Initialize Sentry and logging in one call
init_sentry()
logger = get_logger(__name__)


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="http",
    help="Transport type to use (stdio or http)",
)
@click.option(
    "--host",
    type=str,
    default=None,
    help="Host to bind to (HTTP transport only)",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Port to bind to (HTTP transport only)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode",
)
def run_server(
    transport: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    debug: bool = False,
) -> None:
    """Run the MCP server."""
    
    # Override settings if provided
    if host:
        settings.mcp_server_host = host
    if port:
        settings.mcp_server_port = port
    if debug:
        settings.debug = True
        settings.mcp_log_level = "DEBUG"
    
    if transport == "http":
        logger.info(f"Starting MCP server: transport={transport}, host={settings.mcp_server_host}, port={settings.mcp_server_port}, debug={settings.debug}")
    else:
        logger.info(f"Starting MCP server: transport={transport}, debug={settings.debug}")
    
    try:
        # Create and run server
        server = create_server(transport)
        
        if transport == "stdio":
            asyncio.run(server.run_stdio())
        elif transport == "http":
            asyncio.run(server.run_http())
            
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error("Server failed to start", error=str(e))
        sys.exit(1)


@click.group()
def cli() -> None:
    """MCP Server CLI."""
    pass


@cli.command()
def health() -> None:
    """Check server health."""
    import httpx
    
    try:
        response = httpx.get(f"http://{settings.mcp_server_host}:{settings.mcp_server_port}/health")
        if response.status_code == 200:
            data = response.json()
            click.echo(f"✅ Server is healthy: {data}")
        else:
            click.echo(f"❌ Server returned status {response.status_code}")
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Failed to connect to server: {e}")
        sys.exit(1)


@cli.command()
@click.option("--token", required=True, help="Authorization token (JWT or service account key)")
def list_tools(token: str) -> None:
    """List available tools."""
    import httpx
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.get(
            f"http://{settings.mcp_server_host}:{settings.mcp_server_port}/mcp/tools",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            tools = data.get("tools", [])
            
            click.echo(f"📋 Available tools ({len(tools)}):")
            for tool in tools:
                click.echo(f"  • {tool['name']}: {tool['description']}")
        else:
            click.echo(f"❌ Failed to list tools: {response.status_code}")
            if response.status_code == 401:
                click.echo("   Please check your authorization token")
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ Failed to connect to server: {e}")
        sys.exit(1)


@cli.command()
@click.option("--token", required=True, help="Authorization token (JWT or service account key)")
@click.option("--tool", required=True, help="Tool name to test")
@click.option("--args", default="{}", help="Tool arguments as JSON")
def test_tool(token: str, tool: str, args: str) -> None:
    """Test a specific tool."""
    import httpx
    import json
    
    try:
        # Parse arguments
        tool_args = json.loads(args)
        
        # Prepare request
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        request_data = {
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": tool_args
            }
        }
        
        response = httpx.post(
            f"http://{settings.mcp_server_host}:{settings.mcp_server_port}/mcp",
            headers=headers,
            json=request_data
        )
        
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            click.echo(f"✅ Tool executed successfully:")
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"❌ Tool execution failed: {response.status_code}")
            click.echo(response.text)
            sys.exit(1)
            
    except json.JSONDecodeError:
        click.echo("❌ Invalid JSON in arguments")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Failed to execute tool: {e}")
        sys.exit(1)


@cli.command()
def config() -> None:
    """Show current configuration."""
    click.echo("🔧 Current configuration:")
    click.echo(f"  Server Name: {settings.mcp_server_name}")
    click.echo(f"  Host: {settings.mcp_server_host}")
    click.echo(f"  Port: {settings.mcp_server_port}")
    click.echo(f"  Log Level: {settings.mcp_log_level}")
    click.echo(f"  Debug: {settings.debug}")
    click.echo(f"  Arcade Enabled: {settings.enable_arcade}")
    if settings.enable_arcade:
        click.echo(f"    Arcade API: {settings.arcade_base_url}")
        click.echo(f"    Enabled Services: {', '.join(settings.enabled_services_list)}")
    click.echo(f"  Custom Tools: {'Enabled' if settings.enable_custom_tools else 'Disabled'}")
    click.echo(f"  Image Storage: {'Enabled' if settings.image_storage_enabled else 'Disabled'}")


def _register_arcade_commands():
    """Register Arcade-specific CLI commands if Arcade is enabled."""
    if not settings.enable_arcade:
        return
        
    try:
        from .auth.arcade_auth import arcade_auth_manager
    except ImportError:
        click.echo("Warning: Arcade commands not available - arcadepy not installed")
        return

    @cli.command()
    @click.option("--user-id", required=True, help="User ID for testing")
    @click.option("--tool", required=True, help="Tool name to check authorization for")
    def check_auth_status(user_id: str, tool: str) -> None:
        """Check authorization status without generating new OAuth states."""
        import json
        
        try:
            result = arcade_auth_manager.check_authorization_status_only(user_id, tool)
            click.echo("🔍 Authorization Status (No New OAuth):")
            click.echo(json.dumps(result, indent=2))
        except Exception as e:
            click.echo(f"❌ Status check failed: {e}")
            sys.exit(1)

    @cli.command()
    @click.option("--user-id", required=True, help="User ID to clear cache for")
    @click.option("--tool", help="Specific tool to clear (optional)")
    def clear_auth_cache(user_id: str, tool: str = None) -> None:
        """Clear authorization cache for a user."""
        try:
            arcade_auth_manager.invalidate_auth_cache(user_id, tool)
            if tool:
                click.echo(f"✅ Cleared auth cache for user {user_id} and tool {tool}")
            else:
                click.echo(f"✅ Cleared all auth cache for user {user_id}")
        except Exception as e:
            click.echo(f"❌ Failed to clear cache: {e}")
            sys.exit(1)

    @cli.command()
    def cleanup_expired() -> None:
        """Clean up expired auth cache and OAuth states."""
        try:
            arcade_auth_manager.cleanup_expired_auth_cache()
            click.echo("✅ Cleaned up expired cache entries and OAuth states")
        except Exception as e:
            click.echo(f"❌ Failed to cleanup expired entries: {e}")
            sys.exit(1)


# Register commands
cli.add_command(run_server, name="run")

# Register Arcade commands if enabled
_register_arcade_commands()

if __name__ == "__main__":
    cli()