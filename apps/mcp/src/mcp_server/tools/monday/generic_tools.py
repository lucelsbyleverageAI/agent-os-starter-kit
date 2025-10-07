"""Generic Monday.com tools for the MCP server."""

from typing import Any, List

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_monday_client, handle_monday_error
# Removed MondayToolResponse import - now returning plain markdown strings
from .utils import format_multiple_items, format_monday_item, extract_public_file_urls

logger = get_logger(__name__)


class ListBoardsTool(CustomTool):
    """List all boards accessible with the configured Monday.com API key."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "list_boards"

    @property
    def description(self) -> str:
        return "Returns a list of all boards accessible with the configured Monday.com API key. Each board includes its name and unique board ID. Useful for discovering available boards for further queries."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="The maximum number of boards to return. Defaults to 50. Use this to avoid excessive context size if the account has many boards.",
                required=False,
                default=50,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the list boards tool."""
        try:
            limit = kwargs.get("limit", 50)
            
            client = get_monday_client()
            response = await client.get_boards(limit=limit)
            
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                return "*No boards found.*"
            
            # Format as markdown
            markdown_parts = [f"# Monday.com Boards ({len(boards)} found)\n"]
            
            for board in boards:
                board_id = board.get("id", "")
                board_name = board.get("name", "Unnamed Board")
                description = board.get("description", "")
                state = board.get("state", "")
                permissions = board.get("permissions", "")
                
                markdown_parts.append(f"## {board_name}")
                markdown_parts.append(f"**ID:** {board_id}")
                
                if description:
                    markdown_parts.append(f"**Description:** {description}")
                    
                if state:
                    markdown_parts.append(f"**State:** {state}")
                    
                if permissions:
                    markdown_parts.append(f"**Permissions:** {permissions}")
                
                markdown_parts.append("")
            
            markdown = "\n".join(markdown_parts)
            
            return markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in list_boards: {error_msg}")
            raise ToolExecutionError("list_boards", error_msg)


class GetBoardColumnsTool(CustomTool):
    """Retrieve all columns for a specified board."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_board_columns"

    @property
    def description(self) -> str:
        return "Retrieves all columns for a specified board. Returns column names, IDs, and types, allowing clients to understand the structure of a board and what data can be queried."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="board_id",
                type="string",
                description="The unique identifier of the board to query. Obtainable from list_boards.",
                required=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get board columns tool."""
        try:
            board_id = kwargs["board_id"]
            
            client = get_monday_client()
            response = await client.get_board_columns(board_id)
            
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                return f"*Board with ID '{board_id}' not found.*"
            
            board = boards[0]
            board_name = board.get("name", "Unknown Board")
            columns = board.get("columns", [])
            
            if not columns:
                return f"# {board_name} Columns\n\n*No columns found for this board.*"
            
            # Format as markdown
            markdown_parts = [f"# {board_name} Columns ({len(columns)} found)\n"]
            markdown_parts.append(f"**Board ID:** {board_id}\n")
            
            for column in columns:
                col_id = column.get("id", "")
                col_title = column.get("title", "Unnamed Column")
                col_type = column.get("type", "unknown")
                col_description = column.get("description", "")
                
                markdown_parts.append(f"## {col_title}")
                markdown_parts.append(f"**ID:** `{col_id}`")
                markdown_parts.append(f"**Type:** `{col_type}`")
                
                if col_description:
                    markdown_parts.append(f"**Description:** {col_description}")
                
                markdown_parts.append("")
            
            markdown = "\n".join(markdown_parts)
            
            return markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_board_columns: {error_msg}")
            raise ToolExecutionError("get_board_columns", error_msg)


class ListBoardItemsTool(CustomTool):
    """List items (rows) on a specified board."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "list_board_items"

    @property
    def description(self) -> str:
        return "Lists items (rows) on a specified board, returning item names and IDs. Useful for selecting items to query in detail."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="board_id",
                type="string",
                description="The unique identifier of the board to list items from.",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="The maximum number of items to return. Defaults to 100.",
                required=False,
                default=100,
            ),
            ToolParameter(
                name="max_characters",
                type="integer",
                description="The maximum number of characters in the returned markdown. Use this to prevent context bloat. Defaults to 10000.",
                required=False,
                default=10000,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the list board items tool."""
        try:
            board_id = kwargs["board_id"]
            limit = kwargs.get("limit", 100)
            max_characters = kwargs.get("max_characters", 10000)
            
            client = get_monday_client()
            response = await client.get_board_items(board_id, limit)
            
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                return f"*Board with ID '{board_id}' not found.*"
            
            board = boards[0]
            board_name = board.get("name", "Unknown Board")
            items_page = board.get("items_page", {})
            items = items_page.get("items", [])
            
            if not items:
                return f"# {board_name} Items\n\n*No items found on this board.*"
            
            # Extract all file URLs and include them in markdown
            all_files = []
            for item in items:
                assets = item.get("assets", [])
                all_files.extend(extract_public_file_urls(assets))
            
            # Format items using utility function
            formatted_markdown = format_multiple_items(items, max_characters)
            
            # Add header
            header = f"# {board_name} Items ({len(items)} found)\n"
            header += f"**Board ID:** {board_id}\n\n"
            
            # Add file links if any
            if all_files:
                header += "## Files\n"
                for file_url in all_files:
                    header += f"- {file_url}\n"
                header += "\n"
            
            markdown = header + formatted_markdown
            
            return markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in list_board_items: {error_msg}")
            raise ToolExecutionError("list_board_items", error_msg)


class GetItemTool(CustomTool):
    """Retrieve detailed information for a specific item."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_item"

    @property
    def description(self) -> str:
        return "Retrieves detailed information for a specific item, including all column values, assets, and optionally updates and linked items. Allows fine-grained control over the amount of context returned."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="item_id",
                type="string",
                description="The unique identifier of the item to retrieve.",
                required=True,
            ),
            ToolParameter(
                name="include_updates",
                type="boolean",
                description="Whether to include recent updates (comments) for the item. Defaults to False.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="max_updates",
                type="integer",
                description="The maximum number of updates to include if include_updates is True. Defaults to 10.",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="include_linked_items",
                type="boolean",
                description="Whether to include details of items linked via board relations. Defaults to False.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="max_linked_items",
                type="integer",
                description="The maximum number of linked items to include. Defaults to 100.",
                required=False,
                default=100,
            ),
            ToolParameter(
                name="max_characters",
                type="integer",
                description="The maximum number of characters in the returned markdown. Defaults to 100000.",
                required=False,
                default=100000,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get item tool."""
        try:
            item_id = kwargs["item_id"]
            include_updates = kwargs.get("include_updates", False)
            max_updates = kwargs.get("max_updates", 10)
            include_linked_items = kwargs.get("include_linked_items", False)
            max_linked_items = kwargs.get("max_linked_items", 100)
            max_characters = kwargs.get("max_characters", 100000)
            
            client = get_monday_client()
            response = await client.get_item_details(
                item_id, 
                include_updates=include_updates,
                max_updates=max_updates,
                include_linked_items=include_linked_items
            )
            
            items = response.get("data", {}).get("items", [])
            
            if not items:
                return f"*Item with ID '{item_id}' not found.*"
            
            item = items[0]
            
            # Extract file URLs and include them in markdown
            assets = item.get("assets", [])
            file_urls = extract_public_file_urls(assets)
            
            # Format item using utility function
            formatted_markdown = format_monday_item(
                item,
                include_updates=include_updates,
                max_updates=max_updates,
                include_linked_items=include_linked_items,
                max_linked_items=max_linked_items,
                max_characters=max_characters
            )
            
            # Add file links if any
            if file_urls:
                files_section = "\n\n## Files\n"
                for file_url in file_urls:
                    files_section += f"- {file_url}\n"
                formatted_markdown += files_section
            
            return formatted_markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_item: {error_msg}")
            raise ToolExecutionError("get_item", error_msg)