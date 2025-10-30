"""Generic Monday.com tools for the MCP server."""

from typing import Any, List
import httpx
import email
from email import policy
from email.parser import BytesParser

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_monday_client, handle_monday_error
# Removed MondayToolResponse import - now returning plain markdown strings
from .utils import format_multiple_items, format_monday_item

# Import Docling for document parsing (optional)
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    _DOCLING_AVAILABLE = True
except Exception:
    DocumentConverter = None  # type: ignore
    InputFormat = None  # type: ignore
    PdfFormatOption = None  # type: ignore
    PdfPipelineOptions = None  # type: ignore
    _DOCLING_AVAILABLE = False

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

            # Format items using utility function
            formatted_markdown = format_multiple_items(items, max_characters)

            # Add header
            header = f"# {board_name} Items ({len(items)} found)\n"
            header += f"**Board ID:** {board_id}\n\n"

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

            # Format item using utility function
            formatted_markdown = format_monday_item(
                item,
                include_updates=include_updates,
                max_updates=max_updates,
                include_linked_items=include_linked_items,
                max_linked_items=max_linked_items,
                max_characters=max_characters
            )

            return formatted_markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_item: {error_msg}")
            raise ToolExecutionError("get_item", error_msg)


class DownloadMondayFileTool(CustomTool):
    """Download and parse files from Monday.com items."""

    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "download_monday_file"

    @property
    def description(self) -> str:
        return "Downloads and extracts content from files attached to Monday.com items. Automatically parses supported document formats (PDF, DOCX, XLSX, etc.) and returns the content. Use this tool to access file content without copying complex URLs."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="item_id",
                type="string",
                description="The Monday.com item ID that contains the file.",
                required=True,
            ),
            ToolParameter(
                name="filename",
                type="string",
                description="The exact filename to download (as shown in the Get Item output).",
                required=True,
            ),
            ToolParameter(
                name="parse_content",
                type="boolean",
                description="Whether to parse the file content (for PDFs, DOCX, etc.). If False, returns file metadata only. Defaults to True.",
                required=False,
                default=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the download monday file tool."""
        try:
            item_id = kwargs["item_id"]
            filename = kwargs["filename"]
            parse_content = kwargs.get("parse_content", True)

            # Get item details with assets
            client = get_monday_client()
            response = await client.get_item_details(item_id, include_updates=False, include_linked_items=False)

            items = response.get("data", {}).get("items", [])

            if not items:
                return f"*Item with ID '{item_id}' not found.*"

            item = items[0]
            assets = item.get("assets", [])

            if not assets:
                return f"*No files found attached to item '{item_id}'.*"

            # Find the matching file by filename
            matching_asset = None
            for asset in assets:
                if asset.get("name") == filename:
                    matching_asset = asset
                    break

            if not matching_asset:
                available_files = [asset.get("name", "Unknown") for asset in assets]
                return f"*File '{filename}' not found in item '{item_id}'. Available files: {', '.join(available_files)}*"

            # Get file metadata
            file_url = matching_asset.get("public_url") or matching_asset.get("url")
            file_extension = matching_asset.get("file_extension", "").lower().lstrip('.')  # Remove leading dot if present
            file_id = matching_asset.get("id")

            if not file_url:
                return f"*No download URL available for file '{filename}'.*"

            # If parse_content is False, just return metadata
            if not parse_content:
                return f"# File: {filename}\n\n**File ID:** {file_id}\n**Extension:** {file_extension}\n**Download URL:** {file_url}\n\n*Use parse_content=True to download and parse the file content.*"

            # Check if file format is supported
            supported_extensions = ["pdf", "docx", "pptx", "html", "md", "csv", "xlsx", "asciidoc", "eml"]

            if file_extension not in supported_extensions:
                return f"# File: {filename}\n\n**Status:** Unsupported file format '.{file_extension}'\n**Supported formats:** {', '.join(supported_extensions)}\n\n**Download URL:** {file_url}\n\n*You can download this file manually, but automatic content parsing is not available for this format.*"

            # Handle .eml files separately (email parsing)
            if file_extension == "eml":
                try:
                    logger.info(f"Parsing email file '{filename}' from Monday.com item {item_id}")

                    # Download the file
                    async with httpx.AsyncClient(timeout=60.0) as http_client:
                        file_response = await http_client.get(file_url, follow_redirects=True)
                        file_response.raise_for_status()
                        file_content = file_response.content

                    # Parse email using Python's email library
                    msg = BytesParser(policy=policy.default).parsebytes(file_content)

                    # Extract email headers
                    email_from = msg.get('From', 'Unknown')
                    email_to = msg.get('To', 'Unknown')
                    email_subject = msg.get('Subject', 'No Subject')
                    email_date = msg.get('Date', 'Unknown')
                    email_cc = msg.get('Cc', '')

                    # Get email body
                    body_text = ""
                    if msg.is_multipart():
                        # Try to get plain text first, fallback to HTML
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                body_text = part.get_content()
                                break
                            elif content_type == "text/html" and not body_text:
                                body_text = part.get_content()
                    else:
                        body_text = msg.get_content()

                    # Format as markdown
                    output = f"# Email: {email_subject}\n\n"
                    output += f"**From:** {email_from}\n"
                    output += f"**To:** {email_to}\n"
                    if email_cc:
                        output += f"**Cc:** {email_cc}\n"
                    output += f"**Date:** {email_date}\n"
                    output += f"**Subject:** {email_subject}\n\n"
                    output += "---\n\n"
                    output += f"{body_text}\n"

                    return f"# File: {filename}\n\n**Source Item ID:** {item_id}\n**File Type:** Email (.eml)\n**Parsing Status:** Success\n\n---\n\n{output}"

                except httpx.HTTPStatusError as e:
                    return f"# File: {filename}\n\n**Status:** Download failed with HTTP {e.response.status_code}\n**Error:** {str(e)}\n\n*The download URL may have expired. Try running Get Item again to get a fresh URL, or check file permissions.*"
                except Exception as e:
                    logger.error(f"Error parsing email file '{filename}': {str(e)}")
                    return f"# File: {filename}\n\n**Status:** Error parsing email\n**Error:** {str(e)}\n**Download URL:** {file_url}"

            # Download and parse the file with Docling (for non-email formats)
            if not _DOCLING_AVAILABLE:
                return f"# File: {filename}\n\n**Status:** Document parsing not available (Docling not installed)\n**Download URL:** {file_url}\n\n*Install Docling to enable automatic content parsing.*"

            try:
                logger.info(f"Downloading and parsing file '{filename}' from Monday.com item {item_id}")

                # Download the file
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    file_response = await http_client.get(file_url, follow_redirects=True)
                    file_response.raise_for_status()
                    file_content = file_response.content

                # Parse with Docling
                pipeline_options = PdfPipelineOptions(
                    do_ocr=True,
                    do_table_structure=True,
                    do_picture_analysis=False,
                )
                converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
                )

                # Save to temp file for Docling
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
                    temp_file.write(file_content)
                    temp_path = temp_file.name

                try:
                    conversion_result = converter.convert(temp_path)
                    if hasattr(conversion_result, "document") and conversion_result.document:
                        content = conversion_result.document.export_to_markdown()

                        if content.strip():
                            return f"# File: {filename}\n\n**Source Item ID:** {item_id}\n**File Extension:** {file_extension}\n**Parsing Status:** Success\n\n---\n\n{content}"
                        else:
                            return f"# File: {filename}\n\n**Status:** File parsed but no content extracted\n**Download URL:** {file_url}"
                    else:
                        return f"# File: {filename}\n\n**Status:** Failed to parse document\n**Download URL:** {file_url}"
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

            except httpx.HTTPStatusError as e:
                return f"# File: {filename}\n\n**Status:** Download failed with HTTP {e.response.status_code}\n**Error:** {str(e)}\n\n*The download URL may have expired. Try running Get Item again to get a fresh URL, or check file permissions.*"
            except Exception as e:
                logger.error(f"Error downloading/parsing file '{filename}': {str(e)}")
                return f"# File: {filename}\n\n**Status:** Error during download or parsing\n**Error:** {str(e)}\n**Download URL:** {file_url}"

        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in download_monday_file: {error_msg}")
            raise ToolExecutionError("download_monday_file", error_msg)