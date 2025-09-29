from typing import Optional
from pydantic import BaseModel, Field


class GraphConfigPydantic(BaseModel):
    """
    Configuration schema for the n8n agent.
    
    This agent acts as a bridge to n8n workflows, forwarding messages
    to a configured n8n webhook and streaming back the responses.
    
    Attributes:
        webhook_url: The n8n webhook URL to send requests to
    """
    
    webhook_url: Optional[str] = Field(
        default=None,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "The n8n webhook URL (e.g., 'http://localhost:5678/webhook-test/your-webhook-id')",
                "placeholder": "http://localhost:5678/webhook-test/your-webhook-id",
            }
        },
    )
    """The n8n webhook URL to send requests to"""
