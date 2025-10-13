from typing import Optional, List
from pydantic import BaseModel, Field
from agent_platform.utils.model_utils import get_model_options_for_ui


# Graph metadata
GRAPH_NAME = "Tools Agent"
GRAPH_DESCRIPTION = "A versatile AI assistant with access to various tools for general tasks and productivity"

# System prompts and constants
UNEDITABLE_SYSTEM_PROMPT = "\nIf the tool throws an error requiring authentication, provide the user with a Markdown link to the authentication page and prompt them to authenticate."

DEFAULT_SYSTEM_PROMPT = """## Role
You are a helpful AI assistant with access to a variety of tools.

## Task
Help users accomplish their goals by using the available tools effectively and providing clear, accurate responses.

## Guidelines
- Use tools when they can help answer the user's question or complete their request
- Provide concise, well-structured responses
- Be proactive in suggesting relevant tools or approaches
"""


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
        default=["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"],
        metadata={
            "x_oap_ui_config": {
                "type": "rag_tools",
                "description": "Select which tools the agent can use to interact with document collections",
                "default": ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"],
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
        default="anthropic:claude-sonnet-4-5-20250929",  # Registry key for Claude Sonnet 4.5
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-sonnet-4-5-20250929",
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
                "description": f"The system prompt to use in all generations. The following prompt will always be included at the end of the system prompt:\n---{UNEDITABLE_SYSTEM_PROMPT}\n---",
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
