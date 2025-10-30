"""Business-context Monday.com tools for the MCP server."""

import os
from typing import Any, List, Optional, Tuple
from difflib import SequenceMatcher

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_monday_client, handle_monday_error
# Removed MondayToolResponse import - now returning plain markdown strings
from .utils import format_monday_item

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


class ListProcessesTool(CustomTool):
    """List processes from the Process Master board with simple filtering and pagination."""

    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "list_processes"

    @property
    def description(self) -> str:
        return """Lists processes from the Process Master board with optional filtering and pagination.

RECOMMENDED WORKFLOW:
1. Call get_unique_filter_values() first to understand available filter options
2. Use list_processes() with filters to narrow down results
3. Use get_item(item_id=...) to get full details for specific processes of interest

RETURNED COLUMNS:
- Name, Department, Sub-Department, Status, In-Flight, System/s, Developer, Technology User, Item ID

PAGINATION:
- Default: 50 items starting from offset 0
- Use offset to paginate (e.g., offset=50 for second page, offset=100 for third page)
- Pagination metadata included in response

FILTERING:
- All filter parameters accept lists of values (OR logic within a column, AND logic across columns)
- Example: department=["IT", "Finance"] AND status=["In Progress"]
- Returns processes matching (IT OR Finance) AND (In Progress)
- Use get_unique_filter_values() to discover available values

FOR FULL DETAILS:
- Use get_item(item_id, include_updates=True, include_linked_items=True) for complete process information"""

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="Number of processes to return per page. Defaults to 50.",
                required=False,
                default=50,
            ),
            ToolParameter(
                name="offset",
                type="integer",
                description="Number of processes to skip (for pagination). Defaults to 0. Use limit=50, offset=50 for second page.",
                required=False,
                default=0,
            ),
            ToolParameter(
                name="department",
                type="array",
                description="Filter by department(s). Example: ['IT', 'Finance']. Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="sub_department",
                type="array",
                description="Filter by sub-department(s). Example: ['Application Support']. Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="status",
                type="array",
                description="Filter by status value(s). Example: ['In Progress', 'Completed']. Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="in_flight",
                type="array",
                description="Filter by in-flight status(es). Example: ['Live']. Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="system",
                type="array",
                description="Filter by system(s). Example: ['EPR', 'PAS']. Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="developer",
                type="array",
                description="Filter by developer(s). Get available values from get_unique_filter_values().",
                required=False,
            ),
            ToolParameter(
                name="technology_user",
                type="array",
                description="Filter by technology user(s). Get available values from get_unique_filter_values().",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the list processes tool."""
        try:
            # Extract parameters
            limit = kwargs.get("limit", 50)
            offset = kwargs.get("offset", 0)

            # Filter parameters (all optional arrays)
            filters = {
                "department__1": kwargs.get("department", []),
                "sub_department__1": kwargs.get("sub_department", []),
                "status1__1": kwargs.get("status", []),
                "in_flight__1": kwargs.get("in_flight", []),
                "system__1": kwargs.get("system", []),
                "dropdown7__1": kwargs.get("developer", []),
                "dropdown_mkmc3g1h": kwargs.get("technology_user", []),
            }

            # Use the hardcoded process board ID
            process_board_id = PROCESS_BOARD_ID
            client = get_monday_client()

            # Fetch items - get enough to handle offset + limit
            fetch_limit = min(500, offset + limit + 100)  # Fetch extra for filtering
            response = await client.get_board_items(process_board_id, fetch_limit)

            boards = response.get("data", {}).get("boards", [])
            if not boards:
                return f"*Process board with ID '{process_board_id}' not found.*"

            board = boards[0]
            board_name = board.get("name", "Process Master")
            items_page = board.get("items_page", {})
            all_items = items_page.get("items", [])

            if not all_items:
                return f"# {board_name}\n\n*No processes found.*"

            # Apply filters
            filtered_items = self._apply_filters(all_items, filters)
            total_count = len(filtered_items)

            # Apply pagination
            paginated_items = filtered_items[offset:offset + limit]

            if not paginated_items and offset > 0:
                return f"# {board_name}\n\n*No processes found at offset {offset}. Total matching processes: {total_count}*"

            # Format as markdown table
            markdown = self._format_process_table(
                paginated_items,
                board_name,
                offset,
                limit,
                total_count,
                filters
            )

            return markdown

        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in list_processes: {error_msg}")
            raise ToolExecutionError("list_processes", error_msg)

    def _apply_filters(self, items: List[dict], filters: dict) -> List[dict]:
        """Apply multi-value filters to items (OR within column, AND across columns)."""
        filtered = items

        for column_id, filter_values in filters.items():
            if not filter_values:  # Skip empty filters
                continue

            # Convert filter values to lowercase for case-insensitive matching
            filter_values_lower = [str(v).lower() for v in filter_values]

            # Filter items: must match at least one value in the filter list (OR logic)
            filtered = [
                item for item in filtered
                if self._item_matches_column_filter(item, column_id, filter_values_lower)
            ]

        return filtered

    def _item_matches_column_filter(self, item: dict, column_id: str, filter_values_lower: List[str]) -> bool:
        """Check if item matches any of the filter values for a specific column."""
        column_values = item.get("column_values", [])

        for col in column_values:
            if col.get("id") == column_id:
                text = col.get("text", "")
                if text and text.lower() in filter_values_lower:
                    return True

        return False

    def _get_column_value(self, item: dict, column_id: str) -> str:
        """Extract column value by column ID."""
        column_values = item.get("column_values", [])
        for col in column_values:
            if col.get("id") == column_id:
                return col.get("text", "") or ""
        return ""

    def _format_process_table(
        self,
        items: List[dict],
        board_name: str,
        offset: int,
        limit: int,
        total_count: int,
        filters: dict
    ) -> str:
        """Format processes as a markdown table."""
        # Build filter info string
        active_filters = []
        filter_map = {
            "department__1": "department",
            "sub_department__1": "sub_department",
            "status1__1": "status",
            "in_flight__1": "in_flight",
            "system__1": "system",
            "dropdown7__1": "developer",
            "dropdown_mkmc3g1h": "technology_user",
        }
        for col_id, values in filters.items():
            if values:
                filter_name = filter_map.get(col_id, col_id)
                active_filters.append(f"{filter_name}={values}")

        filter_info = f" (Filters: {', '.join(active_filters)})" if active_filters else ""

        # Build header
        markdown_parts = [
            f"# {board_name} - Processes\n",
            f"**Total matching processes:** {total_count}",
            f"**Showing:** {len(items)} processes (offset {offset} to {offset + len(items)}){filter_info}",
        ]

        # Pagination info
        if offset + limit < total_count:
            next_offset = offset + limit
            markdown_parts.append(f"**Next page:** Use offset={next_offset} to see more")

        if offset > 0:
            prev_offset = max(0, offset - limit)
            markdown_parts.append(f"**Previous page:** Use offset={prev_offset}")

        markdown_parts.append("")  # Blank line

        # Build table header
        markdown_parts.append("| Name | Department | Sub-Dept | Status | In-Flight | System/s | Developer | Tech User | Item ID |")
        markdown_parts.append("|------|------------|----------|--------|-----------|----------|-----------|-----------|---------|")

        # Build table rows
        for item in items:
            name = item.get("name", "Unnamed")[:40]  # Truncate long names
            dept = self._get_column_value(item, "department__1")[:20]
            sub_dept = self._get_column_value(item, "sub_department__1")[:20]
            status = self._get_column_value(item, "status1__1")[:20]
            in_flight = self._get_column_value(item, "in_flight__1")[:20]
            system = self._get_column_value(item, "system__1")[:20]
            developer = self._get_column_value(item, "dropdown7__1")[:20]
            tech_user = self._get_column_value(item, "dropdown_mkmc3g1h")[:20]
            item_id = item.get("id", "")

            markdown_parts.append(
                f"| {name} | {dept} | {sub_dept} | {status} | {in_flight} | {system} | {developer} | {tech_user} | {item_id} |"
            )

        return "\n".join(markdown_parts)


class GetUniqueFilterValuesTool(CustomTool):
    """Get unique values for all filterable columns in the Process Master board."""

    toolkit_name = "monday"
    toolkit_display_name = "Monday.com"

    @property
    def name(self) -> str:
        return "get_unique_filter_values"

    @property
    def description(self) -> str:
        return """Returns all unique values for filterable columns in the Process Master board.

USE THIS FIRST: Before filtering processes, call this tool to discover what filter values are available.

RETURNED COLUMNS:
- Department
- Sub-Department
- Status
- In-Flight
- System/s
- Developer
- Technology User

OUTPUT: Lists all unique values found for each column, helping you construct precise filters for list_processes()."""

    def get_parameters(self) -> List[ToolParameter]:
        return []  # No parameters needed

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get unique filter values tool."""
        try:
            # Use the hardcoded process board ID
            process_board_id = PROCESS_BOARD_ID
            client = get_monday_client()

            # Fetch all items (up to 500)
            response = await client.get_board_items(process_board_id, 500)

            boards = response.get("data", {}).get("boards", [])
            if not boards:
                return f"*Process board with ID '{process_board_id}' not found.*"

            board = boards[0]
            items_page = board.get("items_page", {})
            all_items = items_page.get("items", [])

            if not all_items:
                return "*No processes found.*"

            # Column IDs to extract unique values from
            columns = {
                "department__1": "Department",
                "sub_department__1": "Sub-Department",
                "status1__1": "Status",
                "in_flight__1": "In-Flight",
                "system__1": "System/s",
                "dropdown7__1": "Developer",
                "dropdown_mkmc3g1h": "Technology User",
            }

            # Extract unique values
            unique_values = {col_id: set() for col_id in columns.keys()}

            for item in all_items:
                column_values = item.get("column_values", [])
                for col in column_values:
                    col_id = col.get("id")
                    if col_id in unique_values:
                        text = col.get("text", "")
                        if text:
                            unique_values[col_id].add(text)

            # Format as markdown
            markdown_parts = ["# Process Master - Unique Filter Values\n"]
            markdown_parts.append(f"**Total processes analyzed:** {len(all_items)}\n")

            for col_id, col_title in columns.items():
                values = sorted(unique_values[col_id])  # Sort alphabetically
                markdown_parts.append(f"## {col_title}")
                if values:
                    for value in values:
                        markdown_parts.append(f"- {value}")
                else:
                    markdown_parts.append("- *(No values found)*")
                markdown_parts.append("")  # Blank line

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_monday_error(e)
            logger.error(f"Error in get_unique_filter_values: {error_msg}")
            raise ToolExecutionError("get_unique_filter_values", error_msg)