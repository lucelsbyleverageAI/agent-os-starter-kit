"""Monday API client, authentication, and GraphQL helpers."""

import os
from typing import Any, Dict, Optional
import dotenv

dotenv.load_dotenv()

import httpx
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError, AuthorizationError

logger = get_logger(__name__)

class MondayAPIError(Exception):
    """Monday API specific error."""
    pass


class MondayClient:
    """Monday.com API client."""
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("MONDAY_API_TOKEN")
        if not self.api_token:
            raise AuthorizationError("Monday API token not found. Please set MONDAY_API_TOKEN environment variable.")
        
        self.base_url = "https://api.monday.com/v2"
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "API-Version": "2025-01"
        }
    
    async def graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against Monday.com API."""
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise MondayAPIError(f"HTTP {response.status_code}: {response.text}")
                
                data = response.json()
                
                # Check for GraphQL errors
                if "errors" in data:
                    error_messages = []
                    for error in data["errors"]:
                        if "extensions" in error and error["extensions"].get("code") == "USER_UNAUTHORIZED":
                            raise AuthorizationError(f"Unauthorized: {error['message']}")
                        error_messages.append(error.get("message", "Unknown error"))
                    raise MondayAPIError(f"GraphQL errors: {', '.join(error_messages)}")
                
                return data
                
        except httpx.TimeoutException:
            raise ToolExecutionError("monday_api_client", "Request to Monday.com API timed out")
        except httpx.RequestError as e:
            raise ToolExecutionError("monday_api_client", f"Request to Monday.com API failed: {str(e)}")
    
    async def get_boards(self, limit: int = 20) -> Dict[str, Any]:
        """Get list of boards."""
        query = """
        query GetBoards($limit: Int) {
            boards(limit: $limit) {
                id
                name
                description
                state
                item_terminology
                board_folder_id
                board_kind
                permissions
            }
        }
        """
        variables = {"limit": limit}
        return await self.graphql_query(query, variables)
    
    async def get_board_columns(self, board_id: str) -> Dict[str, Any]:
        """Get columns for a specific board."""
        query = """
        query GetBoardColumns($boardId: [ID!]) {
            boards(ids: $boardId) {
                id
                name
                columns {
                    id
                    title
                    type
                    description
                    settings_str
                }
            }
        }
        """
        variables = {"boardId": [board_id]}
        return await self.graphql_query(query, variables)
    
    async def get_board_items(self, board_id: str, limit: int = 20) -> Dict[str, Any]:
        """Get items from a specific board."""
        query = """
        query GetBoardItems($boardId: [ID!], $limit: Int) {
            boards(ids: $boardId) {
                id
                name
                items_page(limit: $limit) {
                    cursor
                    items {
                        id
                        name
                        state
                        created_at
                        updated_at
                        creator {
                            id
                            name
                        }
                        column_values {
                            id
                            type
                            value
                            text
                            column {
                                title
                                id
                                type
                            }
                        }
                        assets {
                            id
                            name
                            url
                            public_url
                            file_extension
                            created_at
                        }
                    }
                }
            }
        }
        """
        variables = {"boardId": [board_id], "limit": limit}
        return await self.graphql_query(query, variables)
    
    async def get_item_details(
        self, 
        item_id: str, 
        include_updates: bool = False, 
        max_updates: int = 5,
        include_linked_items: bool = False
    ) -> Dict[str, Any]:
        """Get detailed information for a specific item."""
        # Build the query dynamically based on what's requested
        base_query = """
        query GetItemDetails($itemId: [ID!], $includeUpdates: Boolean!, $maxUpdates: Int, $includeLinkedItems: Boolean!) {
            items(ids: $itemId) {
                id
                name
                state
                created_at
                updated_at
                creator {
                    id
                    name
                }
                board {
                    id
                    name
                }
                column_values {
                    id
                    type
                    value
                    text
                    column {
                        title
                        id
                        type
                    }
                    ... on BoardRelationValue @include(if: $includeLinkedItems) {
                        linked_item_ids
                        linked_items {
                            id
                            name
                            board {
                                id
                                name
                            }
                            column_values {
                                id
                                type
                                value
                                text
                                column {
                                    title
                                    id
                                    type
                                }
                            }
                        }
                    }
                }
                assets {
                    id
                    name
                    url
                    public_url
                    file_extension
                    created_at
                }
                updates(limit: $maxUpdates) @include(if: $includeUpdates) {
                    id
                    body
                    text_body
                    created_at
                    creator {
                        id
                        name
                    }
                    replies {
                        id
                        body
                        text_body
                        created_at
                        creator {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        
        variables = {
            "itemId": [item_id],
            "includeUpdates": include_updates,
            "maxUpdates": max_updates,
            "includeLinkedItems": include_linked_items
        }
        
        return await self.graphql_query(base_query, variables)


# Global client instance
_monday_client: Optional[MondayClient] = None


def get_monday_client() -> MondayClient:
    """Get or create Monday API client instance."""
    global _monday_client
    if _monday_client is None:
        _monday_client = MondayClient()
    return _monday_client


def handle_monday_error(error: Exception) -> str:
    """Standardise error messages for MCP."""
    if isinstance(error, AuthorizationError):
        return f"Authorization error: {str(error)}"
    elif isinstance(error, MondayAPIError):
        return f"Monday API error: {str(error)}"
    elif isinstance(error, ToolExecutionError):
        return f"Execution error: {str(error)}"
    else:
        return f"Unexpected error: {str(error)}"