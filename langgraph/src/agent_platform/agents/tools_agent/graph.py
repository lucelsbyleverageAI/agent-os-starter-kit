from langchain_core.runnables import RunnableConfig
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

# Import shared services and utilities
from agent_platform.services.mcp_token import fetch_tokens
from agent_platform.utils.tool_utils import (
    create_rag_tool,
    create_rag_tool_with_universal_context,
    create_langchain_mcp_tool_with_auth_data,
    create_langchain_mcp_tool_with_universal_context,
    wrap_mcp_authenticate_tool,
    create_collection_tools,
)

# Import agent-specific configuration
from agent_platform.agents.tools_agent.config import GraphConfigPydantic, UNEDITABLE_SYSTEM_PROMPT

# Import logging utilities
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


async def graph(config: RunnableConfig):
    """
    Create and configure the tools agent graph.
    
    This function creates a ReAct (Reasoning and Acting) agent with dynamic
    tool integration capabilities. The agent can utilize various tools including
    RAG (Retrieval-Augmented Generation) tools for document search and MCP
    (Model Context Protocol) tools from external servers.
    
    Args:
        config: LangGraph runnable configuration containing:
            - configurable: User configuration parameters including:
                - model_name: LLM model to use
                - temperature: Model temperature setting
                - max_tokens: Maximum tokens for model responses
                - rag: RAG configuration with URL and collections
                - mcp_config: MCP server configuration with URL and tools
            - metadata: Request metadata (user info, etc.)
            - x-supabase-access-token: Authentication token for RAG services
            
    Returns:
        A configured ReAct agent capable of using the loaded tools
        
    Tool Loading Process:
        1. Parse configuration and extract authentication tokens
        2. Load RAG tools from specified collections (if configured)
        3. Connect to MCP servers and discover available tools (if configured)
        4. Filter tools based on configuration requirements
        5. Wrap tools with authentication and error handling
        6. Create ReAct agent with all loaded tools
        
    Authentication:
        - RAG tools: Uses Supabase access token from request headers
        - MCP tools: Supports OAuth Bearer tokens and custom headers
        - Error handling: Provides user-friendly authentication prompts
        
    Error Handling:
        - Graceful degradation when services are unavailable
        - Tool loading failures don't prevent agent creation
        - Authentication errors include helpful user guidance
    """
    
    # Standard logging via Sentry integration; no verbosity overrides
    logger.info("[TOOLS_AGENT] start")
    
    # Step 1: Parse and validate configuration
    cfg = GraphConfigPydantic(**config.get("configurable", {}))
    tools = []

    # Step 2: Extract authentication token for RAG and other services
    # Try multiple locations where the JWT token might be stored
    supabase_token = (
        config.get("configurable", {}).get("x-supabase-access-token") or  # Standard location
        config.get("metadata", {}).get("supabaseAccessToken") or          # Alternative location
        config.get("configurable", {}).get("supabaseAccessToken")         # Another alternative
    )
    
    # Step 3: Load collection tools (RAG + file system) if configured
    if cfg.rag and cfg.rag.langconnect_api_url and cfg.rag.collections and supabase_token:
        try:
            # Get enabled tools list (default to hybrid_search only for backward compatibility)
            enabled_tools = cfg.rag.enabled_tools or ["hybrid_search"]
            
            # Create all enabled tools using the new orchestrator function
            collection_tools = await create_collection_tools(
                langconnect_api_url=cfg.rag.langconnect_api_url,
                collection_ids=cfg.rag.collections,
                enabled_tools=enabled_tools,
                access_token=supabase_token,
                config_getter=lambda: config,
            )
            
            tools.extend(collection_tools)
            logger.info(
                "[TOOLS_AGENT] collection_tools_loaded count=%s enabled_tools=%s",
                len(collection_tools),
                enabled_tools,
            )
        except Exception:
            # Log and continue on tool creation errors
            logger.exception("[TOOLS_AGENT] collection_tools_create_failed")

    # Step 4: Load MCP tools if configured
    if (
        cfg.mcp_config
        and cfg.mcp_config.url
        and cfg.mcp_config.tools
        and (mcp_auth_data := await fetch_tokens(config))
    ):
        # Construct MCP server URL
        server_url = cfg.mcp_config.url.rstrip("/") + "/mcp"
        
        # Create headers based on authentication mode (simplified)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_type = mcp_auth_data.get("auth_type")
        
        if auth_type == "mcp_access_token":
            # Preferred: MCP access token minted by frontend
            access_token = mcp_auth_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
        elif auth_type == "supabase_jwt":
            # Legacy (should not happen anymore)
            jwt_token = mcp_auth_data.get("jwt_token")
            if jwt_token:
                headers["Authorization"] = f"Bearer {jwt_token}"
        elif auth_type == "service_account":
            # Service account authentication - use service account key
            access_token = mcp_auth_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

        # Track which tools to find and which have been added
        tool_names_to_find = set(cfg.mcp_config.tools)
        fetched_mcp_tools_list: list[StructuredTool] = []
        names_of_tools_added = set()

        try:
            # Use official MCP client for listing tools (consistent with deep agents)
            async with streamablehttp_client(server_url, headers=headers) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    page_cursor = None
                    while True:
                        tool_list_page = await session.list_tools(cursor=page_cursor)
                        if not tool_list_page or not tool_list_page.tools:
                            break
                        for mcp_tool in tool_list_page.tools:
                            tool_name = getattr(mcp_tool, "name", None)
                            if not tool_name or tool_name in names_of_tools_added:
                                continue
                            if tool_names_to_find and tool_name not in tool_names_to_find:
                                continue
                            wrapped_tool = create_langchain_mcp_tool_with_universal_context(
                                mcp_tool, server_url, mcp_auth_data, lambda: config
                            )
                            fetched_mcp_tools_list.append(wrapped_tool)
                            names_of_tools_added.add(tool_name)
                            if tool_names_to_find and len(names_of_tools_added) == len(tool_names_to_find):
                                break
                        page_cursor = getattr(tool_list_page, "nextCursor", None)
                        if not page_cursor or (tool_names_to_find and len(names_of_tools_added) == len(tool_names_to_find)):
                            break

            # Add all successfully loaded MCP tools
            tools.extend(fetched_mcp_tools_list)
            logger.info("[TOOLS_AGENT] mcp_tools_loaded count=%s", len(fetched_mcp_tools_list))

        except Exception:
            # Log and continue on MCP connection errors
            logger.exception("[TOOLS_AGENT] mcp_connection_or_loading_error")

    # Step 5: Initialize the LLM model with configured parameters
    model = init_chat_model(
        cfg.model_name,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )

    # Step 6: Create and return the ReAct agent
    logger.info("[TOOLS_AGENT] agent_created tools_count=%s", len(tools))
    return create_react_agent(
        prompt=cfg.system_prompt + UNEDITABLE_SYSTEM_PROMPT,
        model=model,
        tools=tools,
        config_schema=GraphConfigPydantic,
    )
