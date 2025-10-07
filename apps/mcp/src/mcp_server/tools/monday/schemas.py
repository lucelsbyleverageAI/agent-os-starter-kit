"""Pydantic schemas for Monday.com tool parameters and responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Request Schemas
class ListBoardsRequest(BaseModel):
    """Parameters for listing boards."""
    limit: int = Field(
        default=20,
        description="The maximum number of boards to return. Defaults to 20. Use this to avoid excessive context size if the account has many boards.",
        ge=1,
        le=100
    )


class GetBoardColumnsRequest(BaseModel):
    """Parameters for getting board columns."""
    board_id: str = Field(
        description="The unique identifier of the board to query. Obtainable from list_boards.",
    )


class ListBoardItemsRequest(BaseModel):
    """Parameters for listing board items."""
    board_id: str = Field(
        description="The unique identifier of the board to list items from.",
    )
    limit: int = Field(
        default=20,
        description="The maximum number of items to return. Defaults to 20.",
        ge=1,
        le=100
    )
    max_characters: int = Field(
        default=5000,
        description="The maximum number of characters in the returned markdown. Use this to prevent context bloat. Defaults to 5000.",
        ge=500,
        le=50000
    )


class GetItemRequest(BaseModel):
    """Parameters for getting detailed item information."""
    item_id: str = Field(
        description="The unique identifier of the item to retrieve.",
    )
    include_updates: bool = Field(
        default=False,
        description="Whether to include recent updates (comments) for the item. Defaults to False.",
    )
    max_updates: int = Field(
        default=5,
        description="The maximum number of updates to include if include_updates is True. Defaults to 5.",
        ge=1,
        le=20
    )
    include_linked_items: bool = Field(
        default=False,
        description="Whether to include details of items linked via board relations. Defaults to False.",
    )
    max_linked_items: int = Field(
        default=5,
        description="The maximum number of linked items to include. Defaults to 5.",
        ge=1,
        le=20
    )
    max_characters: int = Field(
        default=5000,
        description="The maximum number of characters in the returned markdown. Defaults to 5000.",
        ge=500,
        le=50000
    )


class GetCustomersRequest(BaseModel):
    """Parameters for getting customers list."""
    limit: int = Field(
        default=20,
        description="The maximum number of customers to return. Defaults to 20.",
        ge=1,
        le=100
    )


class GetCustomerInfoRequest(BaseModel):
    """Parameters for getting customer information."""
    customer_id: Optional[str] = Field(
        default=None,
        description="The unique identifier of the customer item. If not provided, customer_name must be specified.",
    )
    customer_name: Optional[str] = Field(
        default=None,
        description="The name of the customer to look up. If not provided, customer_id must be specified.",
    )
    include_updates: bool = Field(
        default=True,
        description="Whether to include recent updates for the customer. Defaults to True.",
    )
    max_updates: int = Field(
        default=5,
        description="The maximum number of updates to include. Defaults to 5.",
        ge=1,
        le=20
    )
    include_linked_items: bool = Field(
        default=True,
        description="Whether to include details of items linked to the customer. Defaults to True.",
    )
    max_linked_items: int = Field(
        default=5,
        description="The maximum number of linked items to include. Defaults to 5.",
        ge=1,
        le=20
    )
    max_characters: int = Field(
        default=5000,
        description="The maximum number of characters in the returned markdown. Defaults to 5000.",
        ge=500,
        le=50000
    )


# Response Schemas
class MondayToolResponse(BaseModel):
    """Base response for Monday.com tools."""
    markdown: str = Field(description="Formatted markdown content")
    files: Optional[List[str]] = Field(default=None, description="List of public file URLs")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Raw Monday API response for debugging")


class BoardInfo(BaseModel):
    """Board information."""
    id: str
    name: str
    description: Optional[str] = None


class ColumnInfo(BaseModel):
    """Column information."""
    id: str
    title: str
    type: str
    description: Optional[str] = None


class ItemInfo(BaseModel):
    """Item information."""
    id: str
    name: str
    board_id: Optional[str] = None


class AssetInfo(BaseModel):
    """Asset/file information."""
    id: str
    name: str
    url: str
    public_url: Optional[str] = None
    file_extension: Optional[str] = None
    created_at: Optional[str] = None


class UpdateInfo(BaseModel):
    """Update/comment information."""
    id: str
    body: str
    created_at: str
    creator_name: Optional[str] = None
    creator_id: Optional[str] = None
    replies: Optional[List[Dict[str, Any]]] = None


class LinkedItemInfo(BaseModel):
    """Linked item information."""
    id: str
    name: str
    board_name: Optional[str] = None
    board_id: Optional[str] = None
    status_indicators: Optional[List[str]] = None