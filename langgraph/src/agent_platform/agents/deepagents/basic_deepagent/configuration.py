from typing import Optional, List
from pydantic import BaseModel, Field

from agent_platform.agents.deepagents.builder import SerializableSubAgent
from agent_platform.utils.model_utils import get_model_options_for_ui


# Graph metadata
GRAPH_NAME = "Deep Agent"
GRAPH_DESCRIPTION = "An advanced multi-agent system where a coordinator plans and delegates tasks to sub-agents to prevent context bloat. Ideal for complex tasks that take a long time to complete."

# System prompts and constants.
DEFAULT_SYSTEM_PROMPT = """## Role
You are an expert AI assistant that helps users by using available tools and delegating tasks to specialist sub-agents.

## Task
Help the user accomplish their goals by:
- Using your available tools to gather information or perform actions
- Delegating complex or specialised tasks to appropriate sub-agents
- Coordinating responses from multiple sub-agents when needed
- Providing clear, concise responses to the user

## Guidelines
- Keep your direct responses concise and to the point
- Delegate to sub-agents for complex or specialised tasks
- Use the file system to store context and maintain continuity across conversations
- When receiving results from sub-agents, summarise key points and reference any files created or modified
"""

DEFAULT_SUB_AGENT_PROMPT = """## Role
You are a specialist sub-agent helping with a specific task delegated by the main agent.

## Task
Complete the delegated task using your available tools and provide a comprehensive response back to the main agent.

## Guidelines
- Focus on completing the specific task you've been assigned
- Use the file system to store any context, findings, or work products
- Summarise what you've accomplished in your response
- Include references to any files you've created or modified
- Keep your response clear and actionable
"""

DEFAULT_RECURSION_LIMIT = 100


class RagConfig(BaseModel):
    """
    Configuration for RAG (Retrieval-Augmented Generation) integration.
    
    This configuration enables the agent to search through document collections
    using semantic similarity. Multiple collections can be configured simultaneously.
    
    Attributes:
        langconnect_api_url: Base URL of the LangConnect API server
        collections: List of collection IDs to make available for search
        enabled_tools: List of tool names to enable (controls both search and file system operations)
        
    Example:
        ```python
        rag_config = RagConfig(
            langconnect_api_url ="https://langconnect-api.example.com",
            collections=["docs-123", "knowledge-456"],
            enabled_tools=["hybrid_search", "fs_list_files", "fs_read_file"]
        )
        ```
    """
    langconnect_api_url: Optional[str] = None
    """The URL of the LangConnect server (e.g., 'https://langconnect-api.example.com')"""
    
    collections: Optional[List[str]] = None
    """List of collection IDs to use for document search"""
    
    enabled_tools: Optional[List[str]] = Field(
        default=["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_read_image", "fs_grep_files"],
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag_tools",
                "description": "Select which tools the agent can use to interact with document collections",
                "default": ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_read_image", "fs_grep_files"],
                "tool_groups": [
                    {
                        "name": "Read Operations",
                        "permission": "viewer",
                        "tools": [
                            {
                                "name": "hybrid_search",
                                "label": "Hybrid Search",
                                "description": "Semantic + keyword search (best for most use cases)",
                            },
                            {
                                "name": "fs_list_collections",
                                "label": "List Collections",
                                "description": "Browse available document collections",
                            },
                            {
                                "name": "fs_list_files",
                                "label": "List Files",
                                "description": "Browse documents across collections",
                            },
                            {
                                "name": "fs_read_file",
                                "label": "Read File",
                                "description": "Read document contents with line numbers",
                            },
                            {
                                "name": "fs_read_image",
                                "label": "Read Image",
                                "description": "View uploaded images with AI-generated descriptions",
                            },
                            {
                                "name": "fs_grep_files",
                                "label": "Search in Files (Grep)",
                                "description": "Search for patterns across documents using regex",
                            },
                        ],
                    },
                    {
                        "name": "Write Operations",
                        "permission": "editor",
                        "tools": [
                            {
                                "name": "fs_write_file",
                                "label": "Write File",
                                "description": "Create new documents in collections",
                            },
                            {
                                "name": "fs_edit_file",
                                "label": "Edit File",
                                "description": "Modify existing document contents",
                            },
                        ],
                    },
                    {
                        "name": "Delete Operations",
                        "permission": "owner",
                        "tools": [
                            {
                                "name": "fs_delete_file",
                                "label": "Delete File",
                                "description": "Permanently remove documents",
                            }
                        ],
                    },
                ],
            }
        },
    )
    """List of tool names to enable for the agent"""


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
        default=DEFAULT_SUB_AGENT_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",
                "description": "The system prompt for the sub-agent.",
                "default": DEFAULT_SUB_AGENT_PROMPT,
            }
        },
    )
    model_name: Optional[str] = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-sonnet-4-5-20250929",
                "description": "Select the AI model for this sub-agent. Each model has optimized settings for its tier (Fast, Standard, or Advanced).",
                "options": get_model_options_for_ui(),
            }
        },
    )
    """LLM model to use for this sub-agent (registry key - temperature and max_tokens are configured automatically per model)"""
    
    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={"x_oap_ui_config": {"type": "mcp"}},
    )
    rag_config: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag",
                "description": "Configure document collections and tools for this sub-agent"
            }
        },
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

    template_name: Optional[str] = Field(
        default=GRAPH_NAME,
        metadata={
            "x_oap_ui_config": {
                "type": "agent_name",
                "description": "The name of the agent template.",
            }
        },
    )
    """The name of the agent template"""

    template_description: Optional[str] = Field(
        default=GRAPH_DESCRIPTION,
        metadata={
            "x_oap_ui_config": {
                "type": "agent_description",
                "description": "The description of the agent template.",
            }
        },
    )
    """The description of the agent template"""

    model_name: Optional[str] = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-sonnet-4-5-20250929",
                "description": "Select the AI model to use. Each model has optimized settings for its tier (Fast, Standard, or Advanced).",
                "options": get_model_options_for_ui(),
            }
        },
    )
    """LLM model to use for generation (registry key - temperature and max_tokens are configured automatically per model)"""
    
    system_prompt: Optional[str] = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",
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

    include_general_purpose_agent: Optional[bool] = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "label": "Include General-Purpose Agent",
                "description": "Enable the built-in general-purpose sub-agent for delegating complex, multi-step tasks. This agent has access to all available tools.",
            }
        },
    )
    """Whether to include the built-in general-purpose sub-agent"""

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
