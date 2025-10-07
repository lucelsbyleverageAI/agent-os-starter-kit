# Monday.com Toolkit Implementation Notes

## Overview

This document outlines the plan for integrating a Monday.com toolkit into the MCP server. The toolkit will provide both generic and business-context tools for read/view access to Monday.com boards, using a single MCP-level API key for authentication. User authentication will follow the same pattern as other MCP tools (e.g., OpenAI, Flux).

---

## Folder and File Structure

```
apps/mcp/src/mcp_server/tools/
  monday/
    __init__.py
    base.py                # Monday API client, auth, GraphQL helpers
    utils.py               # Formatting, markdown, context limiting, file URL helpers
    generic_tools.py       # Generic board/item tools
    business_tools.py      # Business-context tools (e.g., customers)
    schemas.py             # Pydantic models for tool params/results
    test_monday_tools.py   # Unit tests
    monday_implementation_notes.md  # (this file)
```

---

## Authentication Approach

- The Monday.com API key will be set at the MCP server level (in config or environment variable).
- All Monday API requests will use this key, not per-user tokens.
- User authentication and context will be handled as with other MCP tools (using the existing user context extraction and validation logic).
- No user-specific Monday authorisation is required for these tools.

---

## Utility Functions Needed

**In `utils.py`:**
- `format_monday_item_markdown(item, options)`: Formats a Monday item (columns, linked items, assets) as markdown, with options for context limits, inclusion of updates, etc.
- `truncate_text(text, max_chars)`: Truncates text to a character limit.
- `extract_public_file_urls(assets)`: Returns a list of public URLs for files/assets.
- `format_updates_markdown(updates, max_updates, max_chars)`: Formats updates and replies as markdown, with limits.
- `format_column_value(column)`: Formats a single column value (status, date, board_relation, etc.) as markdown.
- `format_linked_items(linked_items, options)`: Formats linked items recursively, with context limits.
- `clean_html_content(html)`: Converts Monday HTML to markdown-friendly text.

**In `base.py`:**
- `get_monday_client()`: Returns an authenticated Monday client using the MCP-level API key.
- `monday_graphql(query, variables)`: Executes a GraphQL query with the MCP API key.
- `handle_monday_error(error)`: Standardises error messages for the MCP.

---

## Tool Parameterisation and Defaults

- All tool parameters will be defined in `schemas.py` using Pydantic models.
- Each parameter will have a 1-2 sentence description explaining its purpose and usage.
- Parameters for context control (e.g., `max_characters`, `max_updates`, `include_linked_items`) will have sensible defaults and be editable by the AI.
- Internal config (e.g., board IDs for business tools) will be hidden from the AI where appropriate.

---

## Tool Descriptions and Parameters

### Generic Tools (in `generic_tools.py`)

#### 1. `list_boards`
- **Description:**
  Returns a list of all boards accessible with the configured Monday.com API key. Each board includes its name and unique board ID. Useful for discovering available boards for further queries.
- **Parameters:**
  - `limit` (int, optional): The maximum number of boards to return. Defaults to 20. Use this to avoid excessive context size if the account has many boards.

#### 2. `get_board_columns`
- **Description:**
  Retrieves all columns for a specified board. Returns column names, IDs, and types, allowing clients to understand the structure of a board and what data can be queried.
- **Parameters:**
  - `board_id` (str, required): The unique identifier of the board to query. Obtainable from `list_boards`.

#### 3. `list_board_items`
- **Description:**
  Lists items (rows) on a specified board, returning item names and IDs. Useful for selecting items to query in detail.
- **Parameters:**
  - `board_id` (str, required): The unique identifier of the board to list items from.
  - `limit` (int, optional): The maximum number of items to return. Defaults to 20.
  - `max_characters` (int, optional): The maximum number of characters in the returned markdown. Use this to prevent context bloat. Defaults to 5000.

#### 4. `get_item`
- **Description:**
  Retrieves detailed information for a specific item, including all column values, assets, and optionally updates and linked items. Allows fine-grained control over the amount of context returned.
- **Parameters:**
  - `item_id` (str, required): The unique identifier of the item to retrieve.
  - `include_updates` (bool, optional): Whether to include recent updates (comments) for the item. Defaults to False.
  - `max_updates` (int, optional): The maximum number of updates to include if `include_updates` is True. Defaults to 5.
  - `include_linked_items` (bool, optional): Whether to include details of items linked via board relations. Defaults to False.
  - `max_linked_items` (int, optional): The maximum number of linked items to include. Defaults to 5.
  - `max_characters` (int, optional): The maximum number of characters in the returned markdown. Defaults to 5000.

### Business Tools (in `business_tools.py`)

#### 1. `get_customers`
- **Description:**
  Returns a list of all customers from the designated customer board. Each customer includes their name and item ID. This tool is tailored to the business context and assumes a specific board structure.
- **Parameters:**
  - `limit` (int, optional): The maximum number of customers to return. Defaults to 20.

#### 2. `get_customer_info`
- **Description:**
  Retrieves all available information for a customer, identified by either name or item ID. Returns all column values, recent updates, and linked items, formatted as markdown. Designed to provide a comprehensive but context-limited view of a customer.
- **Parameters:**
  - `customer_id` (str, optional): The unique identifier of the customer item. If not provided, `customer_name` must be specified.
  - `customer_name` (str, optional): The name of the customer to look up. If not provided, `customer_id` must be specified.
  - `include_updates` (bool, optional): Whether to include recent updates for the customer. Defaults to True.
  - `max_updates` (int, optional): The maximum number of updates to include. Defaults to 5.
  - `include_linked_items` (bool, optional): Whether to include details of items linked to the customer. Defaults to True.
  - `max_linked_items` (int, optional): The maximum number of linked items to include. Defaults to 5.
  - `max_characters` (int, optional): The maximum number of characters in the returned markdown. Defaults to 5000.

---

## Handling Linked Items, Files, Updates, and Column Formatting

- **Linked Items:**
  - Controlled by `include_linked_items` and `max_linked_items` parameters.
  - Linked items are formatted as markdown bullets, including name, ID, board, and optionally status/due date.
  - Recursion is limited to prevent infinite loops and context bloat.

- **Files/Assets:**
  - All file assets are extracted and returned as public URLs in markdown format: `[filename](url) (type)`.
  - If files are not public, a helper will attempt to generate a public link or return a warning.

- **Updates:**
  - Controlled by `include_updates` and `max_updates` parameters.
  - Updates and replies are formatted as markdown, with HTML cleaned and converted to markdown-friendly text.
  - Each update includes author, date, and content.

- **Column Formatting:**
  - Each column type (status, date, dropdown, board_relation, etc.) is formatted using a dedicated function.
  - Long text fields are truncated to `max_characters`.

---

## Response Formatting

- All tool responses are returned as markdown, using clear section headers, bullets, and tables where appropriate.
- Each tool returns a dictionary with at least:
  - `markdown`: The formatted markdown string.
  - `files`: (optional) List of public file URLs.
  - `raw_data`: (optional) The raw Monday API response for debugging.
- Errors are returned as markdown-formatted error messages.

---

## Integration with MCP Server

- All Monday tools are registered in the `CUSTOM_TOOLS` registry for discovery by the MCP server.
- Each tool subclasses `CustomTool` and implements `get_parameters` and `_execute_impl`.
- Error handling uses MCP error classes (`ToolExecutionError`, `AuthorizationError`, etc.).
- Tool schemas are discoverable via the `/mcp/tools` endpoint.

---

## Testing

- Unit tests in `test_monday_tools.py` will cover:
  - GraphQL queries (mocked)
  - Markdown formatting
  - Context limiting
  - Error handling

---

## Example: get_customer_info Tool

**Parameters:**
- `customer_id` (optional): The unique identifier of the customer item. If not provided, `customer_name` must be specified.
- `customer_name` (optional): The name of the customer to look up. If not provided, `customer_id` must be specified.
- `include_updates` (default True): Whether to include recent updates for the customer.
- `max_updates` (default 5): The maximum number of updates to include.
- `include_linked_items` (default True): Whether to include details of items linked to the customer.
- `max_linked_items` (default 5): The maximum number of linked items to include.
- `max_characters` (default 5000): The maximum number of characters in the returned markdown.

**Execution:**
- Look up customer by ID or name.
- Fetch all columns, assets, and (optionally) updates and linked items.
- Format as markdown, truncating as needed.
- Return markdown, file URLs, and raw data.

---

## Next Steps

1. Scaffold the folder and files as above.
2. Implement the Monday API client and utility functions.
3. Define schemas for tool parameters and results.
4. Implement generic and business tools as subclasses of `CustomTool`.
5. Register tools in the MCP server.
6. Add and run tests.