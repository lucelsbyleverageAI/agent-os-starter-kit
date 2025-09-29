from typing import Optional, List
from pydantic import BaseModel, Field

from agent_platform.agents.deepagents.builder import SerializableSubAgent


# System prompts and constants.
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant that has access to a variety of tools and can delegate tasks to sub-agents using the 'task' tool.\n\n"
)
DEFAULT_RECURSION_LIMIT = 100


class RagConfig(BaseModel):
    """
    Configuration for RAG (Retrieval-Augmented Generation) integration.
    
    This configuration enables the agent to search through document collections
    using semantic similarity. Multiple collections can be configured simultaneously.
    
    Attributes:
        langconnect_api_url: Base URL of the LangConnect API server
        collections: List of collection IDs to make available for search
        
    Example:
        ```python
        rag_config = RagConfig(
            langconnect_api_url ="https://langconnect-api.example.com",
            collections=["docs-123", "knowledge-456"]
        )
        ```
    """
    langconnect_api_url: Optional[str] = None
    """The URL of the LangConnect server (e.g., 'https://langconnect-api.example.com')"""
    
    collections: Optional[List[str]] = None
    """List of collection IDs to use for document search"""


class MCPConfig(BaseModel):
    """
    Configuration for MCP (Model Context Protocol) integration.
    
    This configuration enables the agent to connect to MCP servers and use
    their tools. The agent can selectively enable specific tools from the server.
    
    Attributes:
        url: Base URL of the MCP server
        tools: List of tool names to make available (if None, all tools are enabled)
        
    Example:
        ```python
        mcp_config = MCPConfig(
            url="https://mcp-server.example.com",
            tools=["search_documents", "create_file"]
        )
        ```
    """
    url: Optional[str] = Field(
        default=None,
        optional=True,
    )
    """The base URL of the MCP server"""
    
    tools: Optional[List[str]] = Field(
        default=None,
        optional=True,
    )
    """List of specific tools to enable (None = all tools available)"""


class SubAgentConfig(BaseModel):
    """Configuration for a single sub-agent."""

    name: str = Field(
        ...,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "The name of the sub-agent.",
            }
        },
    )
    description: str = Field(
        ...,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "description": "The description of the sub-agent for the main agent to decide when to use it.",
            }
        },
    )
    prompt: str = Field(
        ...,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "description": "The system prompt for the sub-agent.",
            }
        },
    )
    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={"x_oap_ui_config": {"type": "mcp"}},
    )
    rag_config: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={"x_oap_ui_config": {"type": "rag"}},
    )


class GraphConfigPydantic(BaseModel):
    """
    Complete configuration schema for the tools agent.
    
    This is the main configuration class that defines all available options
    for the tools agent, including model parameters, tool integrations,
    and behavior customization.
    
    The configuration includes UI metadata for automatic form generation
    in the agent platform interface.
    
    Attributes:
        model_name: LLM model identifier
        temperature: Randomness control (0-2)
        max_tokens: Maximum response length
        system_prompt: Custom system instructions
        mcp_config: MCP server integration settings
        rag: RAG document search settings
        sub_agents: Configuration for dynamic sub-agents
        recursion_limit: The maximum number of steps the agent can take.
    """
    
    model_name: Optional[str] = Field(
        default="anthropic:claude-3-7-sonnet-latest",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-3-7-sonnet-latest",
                "description": "The model to use in all generations",
                "options": [
                    {
                        "label": "Claude 3.7 Sonnet",
                        "value": "anthropic:claude-3-7-sonnet-latest",
                    },
                    {
                        "label": "Claude 3.5 Sonnet",
                        "value": "anthropic:claude-3-5-sonnet-latest",
                    },
                    {"label": "GPT 4o", "value": "openai:gpt-4o"},
                    {"label": "GPT 4o mini", "value": "openai:gpt-4o-mini"},
                    {"label": "GPT 4.1", "value": "openai:gpt-4.1"},
                ],
            }
        },
    )
    """LLM model to use for generation"""
    
    temperature: Optional[float] = Field(
        default=0.7,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 0.7,
                "min": 0,
                "max": 2,
                "step": 0.1,
                "description": "Controls randomness (0 = deterministic, 2 = creative)",
            }
        },
    )
    """Temperature parameter for controlling response randomness"""
    
    max_tokens: Optional[int] = Field(
        default=4000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 4000,
                "min": 1,
                "description": "The maximum number of tokens to generate",
            }
        },
    )
    """Maximum number of tokens in the response"""
    
    system_prompt: Optional[str] = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "placeholder": "Enter a system prompt...",
                "description": f"The system prompt to use in all generations.",
                "default": DEFAULT_SYSTEM_PROMPT,
            }
        },
    )
    """Custom system prompt for the agent"""
    
    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "mcp",
                # Example default configuration:
                # "default": {
                #     "tools": ["Math_Divide", "Math_Mod"]
                # }
            }
        },
    )
    """MCP server integration configuration"""
    
    rag: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag",
                # Example default configuration:
                # "default": {
                #     "collections": [
                #         "fd4fac19-886c-4ac8-8a59-fff37d2b847f",
                #         "659abb76-fdeb-428a-ac8f-03b111183e25",
                #     ]
                # },
            }
        },
    )
    """RAG document search configuration"""

    sub_agents: Optional[List[SubAgentConfig]] = Field(
        default=[],
        metadata={
            "x_oap_ui_config": {
                "type": "agents",
                "mode": "builder",
                "label": "Sub-Agents",
                "description": "Configure sub-agents to delegate tasks to. Each sub-agent can have its own prompt and tools.",
                "default": [],
            }
        },
    )
    """Configuration for dynamic sub-agents"""

    recursion_limit: Optional[int] = Field(
        default=DEFAULT_RECURSION_LIMIT,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": DEFAULT_RECURSION_LIMIT,
                "min": 1,
                "max": 1000,
                "description": "The maximum number of steps the agent can take.",
            }
        },
    )
    """The maximum number of steps the agent can take."""
