from typing import Optional, ClassVar
from pydantic import BaseModel, Field


class GraphConfigPydantic(BaseModel):
    """
    Configuration schema for the n8n agent.

    This agent acts as a bridge to n8n workflows, forwarding messages
    to a configured n8n webhook and streaming back the responses.

    The agent sends a JSON payload to the webhook containing:
    - thread_id: Unique identifier for the conversation thread
    - user_message: The user's input message as plain text
    - config: JSON-serializable LangGraph configuration metadata, which may include:
      * thread_id: Same as top-level thread_id
      * webhook_url: The configured webhook URL
      * Any custom JSON-serializable configuration passed from the calling application

    Note: Non-serializable objects (like user objects, functions) are automatically
    filtered out to ensure the payload can be sent as JSON.

    Attributes:
        webhook_url: The n8n webhook URL to send requests to
    """

    # Graph metadata (class variables, not fields)
    GRAPH_NAME: ClassVar[str] = "n8n Workflow Agent"
    GRAPH_DESCRIPTION: ClassVar[str] = "Connect to any n8n agent built using the n8n agent template via a webhook."

    template_name: Optional[str] = Field(
        default="n8n Workflow Agent",
        metadata={
            "x_oap_ui_config": {
                "type": "agent_name",
                "description": "The name of the agent template.",
            }
        },
    )
    """The name of the agent template"""

    template_description: Optional[str] = Field(
        default="Connects to n8n workflows for powerful automation and integration capabilities",
        metadata={
            "x_oap_ui_config": {
                "type": "agent_description",
                "description": "The description of the agent template.",
            }
        },
    )
    """The description of the agent template"""

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
