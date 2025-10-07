"""Business-context Monday.com tools for the MCP server."""

import os
from typing import Any, List, Optional, Tuple
from difflib import SequenceMatcher

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_monday_client, handle_monday_error
# Removed MondayToolResponse import - now returning plain markdown strings
from .utils import format_monday_item, extract_public_file_urls

logger = get_logger(__name__)

# Customer Master Board ID - hardcoded as per business requirements
CUSTOMER_MASTER_BOARD_ID = "1644881752"

# Process Board ID - hardcoded as per business requirements
PROCESS_BOARD_ID = "1653909648"


def fuzzy_match_customer_name(target_name: str, customer_items: List[dict]) -> Optional[Tuple[str, float]]:
    """
    Find the best matching customer using fuzzy string matching.
    Returns tuple of (customer_id, similarity_score) or None if no good match.
    """
    if not target_name or not customer_items:
        return None
    
    target_lower = target_name.lower().strip()
    best_match = None
    best_score = 0.0
    
    for item in customer_items:
        item_name = item.get("name", "").lower().strip()
        if not item_name:
            continue
            
        # Calculate similarity using SequenceMatcher
        similarity = SequenceMatcher(None, target_lower, item_name).ratio()
        
        # Also check if target is a substring of item name or vice versa
        if target_lower in item_name or item_name in target_lower:
            similarity = max(similarity, 0.8)  # Boost substring matches
        
        if similarity > best_score and similarity > 0.6:  # Minimum threshold
            best_score = similarity
            best_match = (item.get("id"), similarity)
    
    return best_match


class GetCustomersTool(CustomTool):
    """Get a list of all customers from the designated customer board."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_customers"

    @property
    def description(self) -> str:
        return "Returns a list of all customers from the designated customer board. Each customer includes their name and item ID. This tool is tailored to the business context and assumes a specific board structure."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="The maximum number of customers to return. Defaults to 100.",
                required=False,
                default=100,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get customers tool."""
        try:
            limit = kwargs.get("limit", 100)
            
            # Use the hardcoded customer master board ID
            customer_board_id = CUSTOMER_MASTER_BOARD_ID
            
            client = get_monday_client()
            response = await client.get_board_items(customer_board_id, limit)
            
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                return f"*Customer board with ID '{customer_board_id}' not found.*"
            
            board = boards[0]
            board_name = board.get("name", "Customer Board")
            items_page = board.get("items_page", {})
            items = items_page.get("items", [])
            
            if not items:
                return f"# {board_name}\n\n*No customers found.*"
            
            # Format as a simple list
            markdown_parts = [f"# Customers from {board_name} ({len(items)} found)\n"]
            markdown_parts.append(f"**Board ID:** {customer_board_id}\n")
            
            for item in items:
                item_id = item.get("id", "")
                item_name = item.get("name", "Unnamed Customer")
                created_at = item.get("created_at", "")
                
                markdown_parts.append(f"## {item_name}")
                markdown_parts.append(f"**Customer ID:** {item_id}")
                
                if created_at:
                    from .utils import format_date
                    markdown_parts.append(f"**Created:** {format_date(created_at)}")
                
                # Show key status/contact info if available
                column_values = item.get("column_values", [])
                key_info = []
                
                for col in column_values:
                    col_type = col.get("type")
                    col_title = col.get("column", {}).get("title", "").lower()
                    text = col.get("text")
                    
                    # Extract key business-relevant columns
                    if col_type == "status" and text:
                        key_info.append(f"Status: {text}")
                    elif col_type == "email" and text:
                        key_info.append(f"Email: {text}")
                    elif col_type == "phone" and text:
                        key_info.append(f"Phone: {text}")
                    elif "contact" in col_title and text:
                        key_info.append(f"Contact: {text}")
                
                if key_info:
                    markdown_parts.append("**Key Info:** " + " | ".join(key_info))
                
                markdown_parts.append("")
            
            markdown = "\n".join(markdown_parts)
            
            return markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_customers: {error_msg}")
            raise ToolExecutionError("get_customers", error_msg)


class GetCustomerInfoTool(CustomTool):
    """Retrieve comprehensive information for a specific customer."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_customer_info"

    @property
    def description(self) -> str:
        return "Retrieves all available information for a customer, identified by either name or item ID. Returns all column values, recent updates, and linked items, formatted as markdown. Designed to provide a comprehensive but context-limited view of a customer."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="customer_id",
                type="string",
                description="The unique identifier of the customer item. If not provided, customer_name must be specified.",
                required=False,
            ),
            ToolParameter(
                name="customer_name",
                type="string",
                description="The name of the customer to look up. If not provided, customer_id must be specified.",
                required=False,
            ),
            ToolParameter(
                name="include_updates",
                type="boolean",
                description="Whether to include recent updates for the customer. Defaults to True.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="max_updates",
                type="integer",
                description="The maximum number of updates to include. Defaults to 10.",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="include_linked_items",
                type="boolean",
                description="Whether to include details of items linked to the customer. Defaults to True.",
                required=False,
                default=True,
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
        """Execute the get customer info tool."""
        try:
            customer_id = kwargs.get("customer_id")
            customer_name = kwargs.get("customer_name")
            include_updates = kwargs.get("include_updates", True)
            max_updates = kwargs.get("max_updates", 10)
            include_linked_items = kwargs.get("include_linked_items", True)
            max_linked_items = kwargs.get("max_linked_items", 100)
            max_characters = kwargs.get("max_characters", 100000)
            
            # Validate that either customer_id or customer_name is provided
            if not customer_id and not customer_name:
                raise ToolExecutionError("get_customer_info", "Either customer_id or customer_name must be provided")
            
            client = get_monday_client()
            
            # If we have customer_name but not ID, we need to find the customer first
            if not customer_id and customer_name:
                customer_id = await self._find_customer_by_name(client, customer_name)
                if not customer_id:
                    return f"*Customer with name '{customer_name}' not found.*"
            
            # Get detailed customer information
            response = await client.get_item_details(
                customer_id,
                include_updates=include_updates,
                max_updates=max_updates,
                include_linked_items=include_linked_items
            )
            
            items = response.get("data", {}).get("items", [])
            
            if not items:
                return f"*Customer with ID '{customer_id}' not found.*"
            
            item = items[0]
            
            # Extract file URLs
            assets = item.get("assets", [])
            file_urls = extract_public_file_urls(assets)
            
            # Format customer using utility function with business context
            formatted_markdown = format_monday_item(
                item,
                include_updates=include_updates,
                max_updates=max_updates,
                include_linked_items=include_linked_items,
                max_linked_items=max_linked_items,
                max_characters=max_characters
            )
            
            # Add customer-specific header context
            customer_name_from_item = item.get("name", "Unknown Customer")
            board = item.get("board", {})
            board_name = board.get("name", "Customer Board")
            
            header = f"# Customer Profile: {customer_name_from_item}\n"
            header += f"**Customer ID:** {customer_id}\n"
            header += f"**Source Board:** {board_name}\n\n"
            
            # Replace the generic header with customer-specific one
            if formatted_markdown.startswith("# "):
                lines = formatted_markdown.split("\n")
                formatted_markdown = "\n".join(lines[1:])  # Remove first line
            
            final_markdown = header + formatted_markdown
            
            # Add file links if any
            if file_urls:
                files_section = "\n\n## Files\n"
                for file_url in file_urls:
                    files_section += f"- {file_url}\n"
                final_markdown += files_section
            
            return final_markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_customer_info: {error_msg}")
            raise ToolExecutionError("get_customer_info", error_msg)
    
    async def _find_customer_by_name(self, client, customer_name: str) -> Optional[str]:
        """Find a customer ID by name using fuzzy matching in the customer master board."""
        try:
            # Use the hardcoded customer master board ID
            customer_board_id = CUSTOMER_MASTER_BOARD_ID
            
            # Get all items from customer board and search by name
            response = await client.get_board_items(customer_board_id, limit=100)
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                logger.warning(f"Customer master board with ID {customer_board_id} not found")
                return None
            
            items = boards[0].get("items_page", {}).get("items", [])
            
            if not items:
                logger.warning("No items found in customer master board")
                return None
            
            # Use fuzzy matching to find the best customer match
            match_result = fuzzy_match_customer_name(customer_name, items)
            
            if match_result:
                customer_id, similarity_score = match_result
                logger.info(f"Found customer match: '{customer_name}' -> ID {customer_id} (similarity: {similarity_score:.2f})")
                return customer_id
            else:
                logger.warning(f"No fuzzy match found for customer name: '{customer_name}'")
                return None
            
        except Exception as e:
            logger.error(f"Error finding customer by name: {str(e)}")
            return None


class GetProcessesTool(CustomTool):
    """Get a list of all processes from the designated process board."""
    
    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_processes"

    @property
    def description(self) -> str:
        return "Returns a list of all processes from the designated process board. Each process includes comprehensive details including updates and linked items when requested. This tool is tailored to the business context and assumes a specific board structure."

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="The maximum number of processes to return. Defaults to 100.",
                required=False,
                default=100,
            ),
            ToolParameter(
                name="include_updates",
                type="boolean",
                description="Whether to include recent updates for each process. Defaults to True.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="max_updates",
                type="integer",
                description="The maximum number of updates to include per process. Defaults to 10.",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="include_linked_items",
                type="boolean",
                description="Whether to include details of items linked to each process. Defaults to False.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="max_linked_items",
                type="integer",
                description="The maximum number of linked items to include per process. Defaults to 20.",
                required=False,
                default=20,
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
        """Execute the get processes tool."""
        try:
            limit = kwargs.get("limit", 100)
            include_updates = kwargs.get("include_updates", True)
            max_updates = kwargs.get("max_updates", 10)
            include_linked_items = kwargs.get("include_linked_items", False)
            max_linked_items = kwargs.get("max_linked_items", 20)
            max_characters = kwargs.get("max_characters", 100000)
            
            # Use the hardcoded process board ID
            process_board_id = PROCESS_BOARD_ID
            
            client = get_monday_client()
            response = await client.get_board_items(process_board_id, limit)
            
            boards = response.get("data", {}).get("boards", [])
            
            if not boards:
                return f"*Process board with ID '{process_board_id}' not found.*"
            
            board = boards[0]
            board_name = board.get("name", "Process Board")
            items_page = board.get("items_page", {})
            items = items_page.get("items", [])
            
            if not items:
                return f"# {board_name}\n\n*No processes found.*"
            
            # Start building the markdown response
            markdown_parts = [f"# Processes from {board_name} ({len(items)} found)\n"]
            markdown_parts.append(f"**Board ID:** {process_board_id}\n")
            
            current_length = len("\n".join(markdown_parts))
            
            for item in items:
                # Get detailed information for each process if updates or linked items are requested
                if include_updates or include_linked_items:
                    try:
                        item_id = item.get("id")
                        if item_id:
                            detailed_response = await client.get_item_details(
                                item_id,
                                include_updates=include_updates,
                                max_updates=max_updates,
                                include_linked_items=include_linked_items
                            )
                            detailed_items = detailed_response.get("data", {}).get("items", [])
                            if detailed_items:
                                item = detailed_items[0]  # Use the detailed version
                    except Exception as e:
                        logger.warning(f"Failed to get detailed info for process {item.get('id')}: {str(e)}")
                        # Continue with basic item info
                
                # Extract file URLs
                assets = item.get("assets", [])
                file_urls = extract_public_file_urls(assets)
                
                # Format process using utility function
                formatted_item = format_monday_item(
                    item,
                    include_updates=include_updates,
                    max_updates=max_updates,
                    include_linked_items=include_linked_items,
                    max_linked_items=max_linked_items,
                    max_characters=max_characters // max(1, len(items))  # Distribute character limit across items
                )
                
                # Add file links if any
                if file_urls:
                    files_section = "\n\n### Files\n"
                    for file_url in file_urls:
                        files_section += f"- {file_url}\n"
                    formatted_item += files_section
                
                # Check character limit
                potential_length = current_length + len(formatted_item) + 100  # Buffer for separators
                if potential_length > max_characters:
                    remaining_items = len(items) - len(markdown_parts) + 2  # Account for header lines
                    if remaining_items > 0:
                        markdown_parts.append(f"\n*Note: Output truncated due to character limit. {remaining_items} more processes available.*")
                    break
                
                # Add a separator and the formatted item
                markdown_parts.append("---\n")
                markdown_parts.append(formatted_item)
                
                current_length = potential_length
            
            markdown = "\n".join(markdown_parts)
            
            return markdown
            
        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_processes: {error_msg}")
            raise ToolExecutionError("get_processes", error_msg)