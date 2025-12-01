"""Configuration management for the Open Deep Research system."""

import os
from enum import Enum
from typing import Any, List, Optional

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agent_platform.utils.model_utils import get_model_options_for_ui


# Graph metadata
GRAPH_NAME = "Deep Research Agent"
GRAPH_DESCRIPTION = "A comprehensive research agent that conducts in-depth research using specialist sub-agents with access to the web. Configure with additional access to MCP tools and document collections."


class SearchAPI(Enum):
    """Enumeration of available search API providers."""
    
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    TAVILY = "tavily"
    NONE = "none"

class RagConfig(BaseModel):
    """Configuration for RAG (Retrieval-Augmented Generation) integration.
    
    Enables the researcher to search through LangConnect document collections
    using semantic and keyword hybrid search, plus optional file system operations.
    """
    langconnect_api_url: Optional[str] = Field(
        default=None,
        optional=True,
    )
    """The base URL of the LangConnect API server"""

    collections: Optional[List[str]] = Field(
        default=None,
        optional=True,
    )
    """List of collection IDs to expose as search tools"""
    
    enabled_tools: Optional[List[str]] = Field(
        default=["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_read_image", "collection_grep_files"],
        optional=True,
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
    """List of tool names to enable (controls both search and file system operations)"""

class MCPConfig(BaseModel):
    """Configuration for Model Context Protocol (MCP) servers."""
    
    url: Optional[str] = Field(
        default=None,
        optional=True,
    )
    """The URL of the MCP server"""
    tools: Optional[List[str]] = Field(
        default=None,
        optional=True,
    )
    """The tools to make available to the LLM"""
    auth_required: Optional[bool] = Field(
        default=False,
        optional=True,
    )
    """Whether the MCP server requires authentication"""

class Configuration(BaseModel):
    """Main configuration class for the Deep Research agent."""

    # Template Metadata
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

    # General Configuration
    max_structured_output_retries: int = Field(
        default=3,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 3,
                "min": 1,
                "max": 10,
                "description": "Maximum number of retries for structured output calls from models"
            }
        }
    )
    allow_clarification: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "Whether to allow the researcher to ask the user clarifying questions before starting research"
            }
        }
    )
    max_concurrent_research_units: int = Field(
        default=5,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 5,
                "min": 1,
                "max": 20,
                "step": 1,
                "description": "Maximum number of research units to run concurrently. This will allow the researcher to use multiple sub-agents to conduct research. Note: with more concurrency, you may run into rate limits."
            }
        }
    )
    # Research Configuration
    search_api: SearchAPI = Field(
        default=SearchAPI.TAVILY,
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "tavily",
                "description": "Search API to use for research. NOTE: Make sure your Researcher Model supports the selected search API.",
                "options": [
                    {"label": "Tavily", "value": SearchAPI.TAVILY.value},
                    {"label": "OpenAI Native Web Search", "value": SearchAPI.OPENAI.value},
                    {"label": "Anthropic Native Web Search", "value": SearchAPI.ANTHROPIC.value},
                    {"label": "None", "value": SearchAPI.NONE.value}
                ]
            }
        }
    )
    max_researcher_iterations: int = Field(
        default=1,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 1,
                "min": 1,
                "max": 10,
                "step": 1,
                "description": "Maximum number of research iterations for the Research Supervisor. This is the number of times the Research Supervisor will reflect on the research and ask follow-up questions."
            }
        }
    )
    max_react_tool_calls: int = Field(
        default=2,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 2,
                "min": 1,
                "max": 30,
                "step": 1,
                "description": "Maximum number of tool calling iterations to make in a single researcher step."
            }
        }
    )
    # Model Configuration
    summarization_model: str = Field(
        default="openai:gpt-4.1-mini",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "openai:gpt-4.1-mini",
                "description": "Model for summarizing research results from Tavily search results. Temperature and max_tokens are configured automatically per model.",
                "options": get_model_options_for_ui(),
            }
        }
    )
    max_content_length: int = Field(
        default=50000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 50000,
                "min": 1000,
                "max": 200000,
                "description": "Maximum character length for webpage content before summarization"
            }
        }
    )
    research_model: str = Field(
        default="openai:gpt-4.1-mini",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "openai:gpt-4.1-mini",
                "description": "Model for conducting research. Temperature and max_tokens are configured automatically per model. NOTE: Make sure your Researcher Model supports the selected search API.",
                "options": get_model_options_for_ui(),
            }
        }
    )
    compression_model: str = Field(
        default="openai:gpt-4.1-mini",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "openai:gpt-4.1-mini",
                "description": "Model for compressing research findings from sub-agents. Temperature and max_tokens are configured automatically per model. NOTE: Make sure your Compression Model supports the selected search API.",
                "options": get_model_options_for_ui(),
            }
        }
    )
    final_report_model: str = Field(
        default="openai:gpt-4.1-mini",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "openai:gpt-4.1-mini",
                "description": "Model for writing the final report from all research findings. Temperature and max_tokens are configured automatically per model.",
                "options": get_model_options_for_ui(),
            }
        }
    )
    # MCP server configuration
    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "mcp",
                "description": "MCP server configuration"
            }
        }
    )
    mcp_prompt: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",
                "description": "Any additional instructions to pass along to the Agent regarding the MCP tools that are available to it."
            }
        }
    )

    # RAG (LangConnect) configuration
    rag: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag",
                "description": "LangConnect RAG configuration (collections to search)"
            }
        }
    )


    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        values: dict[str, Any] = {
            field_name: os.environ.get(field_name.upper(), configurable.get(field_name))
            for field_name in field_names
        }
        return cls(**{k: v for k, v in values.items() if v is not None})

    class Config:
        """Pydantic configuration."""
        
        arbitrary_types_allowed = True