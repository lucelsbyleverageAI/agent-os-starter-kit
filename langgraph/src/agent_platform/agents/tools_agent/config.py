from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from agent_platform.utils.model_utils import get_model_options_for_ui
from agent_platform.agents.deepagents.skills_deepagent.configuration import (
    SkillsConfig,
    SandboxConfig,
)


# Graph metadata
GRAPH_NAME = "Basic ReAct Agent"
GRAPH_DESCRIPTION = "A versatile AI agent that you can configure with access to tools and knowledge collections. Ideal for general and flexible tasks where you are happy to give the AI agent a high degree of autonomy."

# Default system prompt
DEFAULT_SYSTEM_PROMPT = """## Role
You are a helpful AI assistant with access to a variety of tools.

## Task
Help users accomplish their goals by using the available tools effectively and providing clear, accurate responses.

## Guidelines
- Use tools when they can help answer the user's question or complete their request
- Provide concise, well-structured responses
- Be proactive in suggesting relevant tools or approaches
"""

DEFAULT_RECURSION_LIMIT = 40


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
            enabled_tools=["collection_hybrid_search", "collection_list_files", "collection_read_file"]
        )
        ```
    """
    langconnect_api_url: Optional[str] = None
    """The URL of the LangConnect server (e.g., 'https://langconnect-api.example.com')"""
    
    collections: Optional[List[str]] = None
    """List of collection IDs to use for document search"""
    
    enabled_tools: Optional[List[str]] = Field(
        default=["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_read_image", "collection_grep_files"],
        metadata={
            "x_oap_ui_config": {
                "type": "rag_tools",
                "description": "Select which tools the agent can use to interact with document collections",
                "default": ["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_read_image", "collection_grep_files"],
                "tool_groups": [
                    {
                        "name": "Read Operations",
                        "permission": "viewer",
                        "tools": [
                            {
                                "name": "collection_hybrid_search",
                                "label": "Hybrid Search",
                                "description": "Semantic + keyword search (best for large knowledge bases)",
                            },
                            {
                                "name": "collection_list",
                                "label": "List Collections",
                                "description": "Browse available document collections",
                            },
                            {
                                "name": "collection_list_files",
                                "label": "List Files",
                                "description": "Browse documents across collections",
                            },
                            {
                                "name": "collection_read_file",
                                "label": "Read File",
                                "description": "Read document contents with line numbers",
                            },
                            {
                                "name": "collection_read_image",
                                "label": "Read Image",
                                "description": "View uploaded images with AI-generated descriptions",
                            },
                            {
                                "name": "collection_grep_files",
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
                                "name": "collection_write_file",
                                "label": "Write File",
                                "description": "Create new documents in collections",
                            },
                            {
                                "name": "collection_edit_file",
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
                                "name": "collection_delete_file",
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

    tool_approvals: Optional[Dict[str, bool]] = Field(
        default={},
        metadata={
            "x_oap_ui_config": {
                "type": "tool_approvals",
                "description": "Configure which document tools require human approval before execution",
            }
        },
    )
    """Dictionary mapping tool names to approval requirements (True = requires approval)"""


class MCPConfig(BaseModel):
    """
    Configuration for MCP (Model Context Protocol) integration.

    This configuration enables the agent to connect to MCP servers and use
    their tools. The agent can selectively enable specific tools from the server.

    Attributes:
        url: Base URL of the MCP server
        tools: List of tool names to make available (if None, all tools are enabled)
        tool_approvals: Dictionary mapping tool names to approval requirements

    Example:
        ```python
        mcp_config = MCPConfig(
            url="https://mcp-server.example.com",
            tools=["search_documents", "create_file"],
            tool_approvals={"create_file": True}  # Require approval for create_file
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

    tool_approvals: Optional[Dict[str, bool]] = Field(
        default={},
        metadata={
            "x_oap_ui_config": {
                "type": "tool_approvals",
                "description": "Configure which MCP tools require human approval before execution",
            }
        },
    )
    """Dictionary mapping tool names to approval requirements (True = requires approval)"""


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
        recursion_limit: Maximum number of steps the agent can take
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
        default="anthropic/claude-sonnet-4",  # Registry key for Claude Sonnet 4.5
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic/claude-sonnet-4",
                "description": "Select the AI model to use. Each model has optimized settings for its tier (Fast, Standard, or Advanced).",
                "options": get_model_options_for_ui(),  # Dynamically populated from model registry
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
                "description": "Domain-specific instructions for the agent. These appear after the platform's execution context.",
                "default": DEFAULT_SYSTEM_PROMPT,
            }
        },
    )
    """Custom system prompt for the agent"""

    sandbox_enabled: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "title": "Enable Sandbox",
                "description": "Enable E2B sandbox for code execution, file processing, and skills",
                "default": False,
            }
        },
    )
    """Master switch for sandbox features - when False, agent behaves as a standard tools agent"""

    skills_config: Optional[SkillsConfig] = Field(
        default=None,
        metadata={
            "x_oap_ui_config": {
                "type": "skills",
                "title": "Skills",
                "description": "Select skills to enable for this agent",
                "disabled_when": "!sandbox_enabled",
            }
        },
    )
    """Skills configuration (only used when sandbox_enabled=True)"""

    sandbox_config: Optional[SandboxConfig] = Field(
        default_factory=SandboxConfig,
        metadata={
            "x_oap_ui_config": {
                "type": "sandbox_config",
                "title": "Sandbox Settings",
                "description": "Configure the E2B sandbox environment",
                "disabled_when": "!sandbox_enabled",
            }
        },
    )
    """Sandbox configuration (only used when sandbox_enabled=True)"""

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
