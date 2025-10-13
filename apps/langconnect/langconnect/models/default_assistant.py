from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DefaultAssistantResponse(BaseModel):
    """Response model for user's default assistant."""
    user_id: str
    assistant_id: UUID
    assistant_name: Optional[str] = None
    graph_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class SetDefaultAssistantRequest(BaseModel):
    """Request model for setting default assistant."""
    assistant_id: UUID = Field(..., description="Assistant ID to set as default")


class SetDefaultAssistantResponse(BaseModel):
    """Response model after setting default assistant."""
    user_id: str
    assistant_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
