"""Utility to list all available Arcade tools."""

import asyncio
import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import click
from arcadepy.types import ToolDefinition as ArcadeToolDefinition

from ..auth.arcade_auth import arcade_auth_manager
from ..config import settings
from .logging import get_logger

logger = get_logger(__name__)


class ArcadeToolsLister:
    """Utility class to list and explore Arcade tools."""

    def __init__(self):
        self.tools: List[ArcadeToolDefinition] = []
        self.tools_by_toolkit: Dict[str, List[ArcadeToolDefinition]] = defaultdict(list)

    async def fetch_all_tools(self) -> None:
        """Fetch all tools from Arcade API."""
        try:
            arcade_client = arcade_auth_manager.arcade_client
            response = arcade_client.tools.list(limit=1000)
            
            if not response.items:
                logger.warning("No tools returned from Arcade API")
                return
            
            self.tools = response.items
            
            # Group by toolkit
            self.tools_by_toolkit.clear()
            for tool in self.tools:
                if hasattr(tool, 'toolkit') and tool.toolkit:
                    toolkit_name = tool.toolkit.name
                    self.tools_by_toolkit[toolkit_name].append(tool)
                else:
                    self.tools_by_toolkit["No Toolkit"].append(tool)
            
            logger.info(f"Fetched {len(self.tools)} tools from Arcade API")
            
        except Exception as e:
            logger.error(f"Failed to fetch tools from Arcade API: {e}")
            raise

    def get_toolkit_summary(self) -> Dict[str, int]:
        """Get summary of tools by toolkit."""
        return {toolkit: len(tools) for toolkit, tools in self.tools_by_toolkit.items()}

    def get_tool_details(self, tool: ArcadeToolDefinition) -> Dict:
        """Get detailed information about a tool."""
        details = {
            "name": tool.name,
            "description": getattr(tool, 'description', 'No description'),
            "toolkit": tool.toolkit.name if hasattr(tool, 'toolkit') and tool.toolkit else None,
        }
        
        # Add parameters if available
        if hasattr(tool, 'parameters') and tool.parameters:
            details["parameters"] = []
            for param in tool.parameters:
                param_info = {
                    "name": param.name,
                    "type": getattr(param, 'type', 'unknown'),
                    "description": getattr(param, 'description', ''),
                    "required": getattr(param, 'required', False),
                }
                details["parameters"].append(param_info)
        
        return details

    def filter_tools_by_enabled_services(self) -> Tuple[List[ArcadeToolDefinition], List[ArcadeToolDefinition]]:
        """Split tools into enabled and disabled based on current configuration."""
        enabled_services = set(service.lower() for service in settings.enabled_services_list)
        
        enabled_tools = []
        disabled_tools = []
        
        for tool in self.tools:
            if hasattr(tool, 'toolkit') and tool.toolkit:
                toolkit_name = tool.toolkit.name.lower()
                if toolkit_name in enabled_services:
                    enabled_tools.append(tool)
                else:
                    disabled_tools.append(tool)
            else:
                disabled_tools.append(tool)  # Tools without toolkit are disabled
        
        return enabled_tools, disabled_tools

    def print_toolkit_summary(self) -> None:
        """Print a summary of tools grouped by toolkit."""
        click.echo("\n📋 Toolkit Summary:")
        click.echo("=" * 50)
        
        total_tools = 0
        for toolkit, count in sorted(self.get_toolkit_summary().items()):
            total_tools += count
            enabled_indicator = "✅" if toolkit.lower() in [s.lower() for s in settings.enabled_services_list] else "❌"
            click.echo(f"{enabled_indicator} {toolkit}: {count} tools")
        
        click.echo(f"\nTotal: {total_tools} tools across {len(self.tools_by_toolkit)} toolkits")

    def print_detailed_tools(self, toolkit_filter: Optional[str] = None, enabled_only: bool = False) -> None:
        """Print detailed information about tools."""
        enabled_tools, disabled_tools = self.filter_tools_by_enabled_services()
        
        if enabled_only:
            tools_to_show = enabled_tools
            click.echo("\n🛠️  Enabled Tools:")
        else:
            tools_to_show = self.tools
            click.echo("\n🛠️  All Tools:")
        
        click.echo("=" * 80)
        
        # Filter by toolkit if specified
        if toolkit_filter:
            tools_to_show = [
                tool for tool in tools_to_show 
                if hasattr(tool, 'toolkit') and tool.toolkit and 
                tool.toolkit.name.lower() == toolkit_filter.lower()
            ]
            click.echo(f"Filtered by toolkit: {toolkit_filter}")
            click.echo("-" * 40)
        
        # Group tools by toolkit for display
        tools_by_toolkit = defaultdict(list)
        for tool in tools_to_show:
            if hasattr(tool, 'toolkit') and tool.toolkit:
                toolkit_name = tool.toolkit.name
            else:
                toolkit_name = "No Toolkit"
            tools_by_toolkit[toolkit_name].append(tool)
        
        for toolkit_name in sorted(tools_by_toolkit.keys()):
            enabled_indicator = "✅" if toolkit_name.lower() in [s.lower() for s in settings.enabled_services_list] else "❌"
            click.echo(f"\n{enabled_indicator} {toolkit_name} ({len(tools_by_toolkit[toolkit_name])} tools)")
            click.echo("-" * 40)
            
            for tool in sorted(tools_by_toolkit[toolkit_name], key=lambda t: t.name):
                details = self.get_tool_details(tool)
                click.echo(f"  📌 {details['name']}")
                if details['description']:
                    click.echo(f"     {details['description']}")
                
                if details.get('parameters'):
                    click.echo("     Parameters:")
                    for param in details['parameters']:
                        required_marker = "*" if param['required'] else ""
                        click.echo(f"       • {param['name']}{required_marker} ({param['type']}): {param['description']}")
                click.echo()

    def export_to_json(self, filename: str, enabled_only: bool = False) -> None:
        """Export tools data to JSON file."""
        enabled_tools, disabled_tools = self.filter_tools_by_enabled_services()
        
        if enabled_only:
            tools_to_export = enabled_tools
        else:
            tools_to_export = self.tools
        
        export_data = {
            "total_tools": len(tools_to_export),
            "enabled_services": settings.enabled_services_list,
            "toolkits": {},
            "tools": []
        }
        
        # Add toolkit summary
        for toolkit_name, tools_list in self.tools_by_toolkit.items():
            toolkit_tools = [t for t in tools_list if t in tools_to_export]
            if toolkit_tools:
                export_data["toolkits"][toolkit_name] = {
                    "count": len(toolkit_tools),
                    "enabled": toolkit_name.lower() in [s.lower() for s in settings.enabled_services_list]
                }
        
        # Add detailed tool information
        for tool in tools_to_export:
            export_data["tools"].append(self.get_tool_details(tool))
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        click.echo(f"✅ Exported {len(tools_to_export)} tools to {filename}")


# CLI Commands
@click.group()
def cli():
    """Arcade Tools Lister - Explore available Arcade tools."""
    pass


@cli.command()
@click.option('--summary-only', is_flag=True, help='Show only toolkit summary')
@click.option('--toolkit', help='Filter by specific toolkit')
@click.option('--enabled-only', is_flag=True, help='Show only enabled tools')
@click.option('--export', help='Export to JSON file')
def list_tools(summary_only: bool, toolkit: Optional[str], enabled_only: bool, export: Optional[str]):
    """List all available Arcade tools."""
    async def _run():
        lister = ArcadeToolsLister()
        
        try:
            click.echo("🔍 Fetching tools from Arcade API...")
            await lister.fetch_all_tools()
            
            # Always show toolkit summary
            lister.print_toolkit_summary()
            
            if not summary_only:
                lister.print_detailed_tools(toolkit_filter=toolkit, enabled_only=enabled_only)
            
            if export:
                lister.export_to_json(export, enabled_only=enabled_only)
                
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
    
    asyncio.run(_run())


@cli.command()
@click.argument('toolkit_name')
def list_toolkit(toolkit_name: str):
    """List tools for a specific toolkit."""
    async def _run():
        lister = ArcadeToolsLister()
        
        try:
            click.echo(f"🔍 Fetching tools for toolkit: {toolkit_name}")
            await lister.fetch_all_tools()
            
            lister.print_detailed_tools(toolkit_filter=toolkit_name)
            
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
    
    asyncio.run(_run())


@cli.command()
@click.option('--output', default='arcade_tools.json', help='Output filename')
@click.option('--enabled-only', is_flag=True, help='Export only enabled tools')
def export(output: str, enabled_only: bool):
    """Export tools data to JSON."""
    async def _run():
        lister = ArcadeToolsLister()
        
        try:
            click.echo("🔍 Fetching tools from Arcade API...")
            await lister.fetch_all_tools()
            
            lister.export_to_json(output, enabled_only=enabled_only)
            
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
    
    asyncio.run(_run())


# Convenience functions for direct usage
async def list_all_arcade_tools(summary_only: bool = False, enabled_only: bool = False) -> ArcadeToolsLister:
    """Convenience function to list all Arcade tools programmatically."""
    lister = ArcadeToolsLister()
    await lister.fetch_all_tools()
    
    lister.print_toolkit_summary()
    
    if not summary_only:
        lister.print_detailed_tools(enabled_only=enabled_only)
    
    return lister


if __name__ == "__main__":
    cli() 