from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

# Import approval utilities
from agent_platform.utils.tool_approval_utils import merge_tool_approvals
from agent_platform.agents.tools_agent.react_agent_with_approval import create_react_agent_with_approval

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
from agent_platform.utils.model_utils import (
    init_model_simple,
    get_model_info,
    ModelConfig,
    RetryConfig,
    FallbackConfig,
    MessageTrimmingConfig,
    create_trimming_hook,
)
from agent_platform.utils.message_utils import create_image_preprocessor
from agent_platform.utils.prompt_utils import append_datetime_to_prompt

# Import agent-specific configuration
from agent_platform.agents.tools_agent.config import GraphConfigPydantic, UNEDITABLE_SYSTEM_PROMPT, DEFAULT_RECURSION_LIMIT

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
                - recursion_limit: Maximum number of steps the agent can take (default: 40)
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
    configurable_dict = config.get("configurable", {})
    logger.info(
        "[TOOLS_AGENT] config_received configurable_keys=%s",
        list(configurable_dict.keys())
    )

    cfg = GraphConfigPydantic(**configurable_dict)
    tools = []

    # Log parsed configuration for debugging
    logger.info(
        "[TOOLS_AGENT] parsed_config mcp_tools=%s rag_tools=%s",
        cfg.mcp_config.tools if cfg.mcp_config else None,
        cfg.rag.enabled_tools if cfg.rag else None
    )
    logger.info(
        "[TOOLS_AGENT] tool_approvals_raw mcp=%s rag=%s",
        cfg.mcp_config.tool_approvals if cfg.mcp_config else {},
        cfg.rag.tool_approvals if cfg.rag else {}
    )

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

    # Step 5: Initialize the LLM model with optimized settings
    # Temperature and max_tokens are configured automatically based on the model tier
    # - Fast models: temperature=0.7, max_tokens=4000
    # - Standard models: temperature=0.7, max_tokens=8000
    # - Advanced models: temperature=0.5, max_tokens=16000
    model = init_model_simple(model_name=cfg.model_name)
    
    # Step 5b: Create message trimming hook based on model-level settings
    # Each model has its own trimming configuration based on context window
    model_info = get_model_info(cfg.model_name)
    trimming_hook = None

    if model_info.enable_trimming:
        trimming_hook = create_trimming_hook(
            MessageTrimmingConfig(
                enabled=True,
                max_tokens=model_info.trimming_max_tokens,
                strategy="last",  # Keep most recent messages
                start_on="human",
                end_on=("human", "tool"),
                include_system=True,
            )
        )
        logger.info(
            "[TOOLS_AGENT] message_trimming_enabled max_tokens=%s (model: %s)",
            model_info.trimming_max_tokens,
            model_info.display_name
        )
    else:
        logger.info(
            "[TOOLS_AGENT] message_trimming_disabled (model: %s)",
            model_info.display_name
        )

    # Step 5c: Create image preprocessor for handling image storage paths
    # Get LangConnect URL from config
    langconnect_api_url = (
        cfg.rag.langconnect_api_url if cfg.rag else "http://langconnect:8080"
    )

    # Create image preprocessor
    image_hook = create_image_preprocessor(langconnect_api_url)

    # Combine hooks: TRIMMING first (based on storage paths), THEN image processing
    # This ensures trimming decisions are based on the small storage path tokens,
    # not the massive base64 data that comes from image conversion in local dev.
    combined_hook = None
    if trimming_hook and image_hook:
        async def combined_pre_model_hook(state, config):
            # 1. Trim first (when images are just storage paths ~50 tokens each)
            trimming_result = trimming_hook(state)
            state = {**state, **trimming_result}
            # 2. Then convert images to signed URLs (or base64 in local dev)
            state = await image_hook(state, config)
            return state
        combined_hook = combined_pre_model_hook
    elif image_hook:
        combined_hook = image_hook
    elif trimming_hook:
        combined_hook = trimming_hook

    logger.info(
        "[TOOLS_AGENT] hooks_configured image=%s trimming=%s",
        image_hook is not None,
        trimming_hook is not None
    )

    # Step 6: Collect tool approvals from configuration
    # Merge approvals from both MCP and RAG sources
    mcp_approvals = cfg.mcp_config.tool_approvals if cfg.mcp_config else {}
    rag_approvals = cfg.rag.tool_approvals if cfg.rag else {}
    tool_approvals = merge_tool_approvals(mcp_approvals, rag_approvals)

    logger.info(
        "[TOOLS_AGENT] tool_approvals_configured count=%s tools_requiring_approval=%s",
        len(tool_approvals),
        [name for name, required in tool_approvals.items() if required]
    )

    # Step 7: Create and return the ReAct agent with approval support
    # Get recursion limit from config, default to DEFAULT_RECURSION_LIMIT if not specified
    recursion_limit = cfg.recursion_limit if cfg.recursion_limit is not None else DEFAULT_RECURSION_LIMIT

    logger.info("[TOOLS_AGENT] agent_created tools_count=%s recursion_limit=%s", len(tools), recursion_limit)

    return create_react_agent_with_approval(
        prompt=append_datetime_to_prompt(cfg.system_prompt + UNEDITABLE_SYSTEM_PROMPT),
        model=model,
        tools=tools,
        tool_approvals=tool_approvals,
        config_schema=GraphConfigPydantic,
        pre_model_hook=combined_hook,  # Combined image + trimming hooks
    ).with_config({"recursion_limit": recursion_limit})
