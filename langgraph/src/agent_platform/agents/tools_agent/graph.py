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
from agent_platform.utils.message_utils import create_image_preprocessor, create_orphan_resolution_hook

# Import agent-specific configuration and state
from agent_platform.agents.tools_agent.config import GraphConfigPydantic, DEFAULT_RECURSION_LIMIT
from agent_platform.agents.tools_agent.state import ToolsAgentState
from agent_platform.agents.tools_agent.prompts import build_system_prompt

# Import sandbox-related utilities (lazy import for sandbox tools)
from agent_platform.agents.deepagents.skills_deepagent.sandbox_tools import create_sandbox_tools
from agent_platform.agents.deepagents.skills_deepagent.file_attachment_processing import create_file_attachment_nodes
from agent_platform.agents.deepagents.skills_deepagent.tools.publish_file import create_publish_file_tool

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
    
    configurable_dict = config.get("configurable", {})
    cfg = GraphConfigPydantic(**configurable_dict)
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
            logger.debug("[TOOLS_AGENT] collection_tools_loaded count=%s", len(collection_tools))
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

            tools.extend(fetched_mcp_tools_list)
            logger.debug("[TOOLS_AGENT] mcp_tools_loaded count=%s", len(fetched_mcp_tools_list))

        except Exception:
            # Log and continue on MCP connection errors
            logger.exception("[TOOLS_AGENT] mcp_connection_or_loading_error")

    # Step 4b: Extract thread_id and user_id for sandbox tools (if sandbox enabled)
    thread_id = config.get("configurable", {}).get("thread_id")
    user_id = config.get("metadata", {}).get("user_id")

    # Step 4c: Add sandbox tools if sandbox is enabled
    file_attachment_processor = None
    if cfg.sandbox_enabled:
        if not thread_id:
            logger.warning("[TOOLS_AGENT] sandbox_enabled but no thread_id")
        else:

            # Get LangConnect URL for skills download
            langconnect_api_url = (
                cfg.rag.langconnect_api_url if cfg.rag else "http://langconnect:8080"
            )

            # Create sandbox tools (run_code, run_command)
            run_code_tool, run_command_tool = create_sandbox_tools(thread_id)
            tools.extend([run_code_tool, run_command_tool])

            # Create publish_file_to_user tool if we have user context
            if user_id and supabase_token:
                publish_tool = create_publish_file_tool(
                    thread_id=thread_id,
                    user_id=user_id,
                    langconnect_url=langconnect_api_url,
                    access_token=supabase_token,
                )
                tools.append(publish_tool)
            else:
                logger.debug("[TOOLS_AGENT] publish_file_to_user not added (missing user_id or access_token)")

            # Create file attachment processing nodes for sandbox initialization
            # Get skills from config (if configured)
            skills = []
            if cfg.skills_config and cfg.skills_config.skills:
                skills = [
                    {"skill_id": s.skill_id, "name": s.name}
                    for s in cfg.skills_config.skills
                    if s.skill_id and s.name
                ]
                logger.debug("[TOOLS_AGENT] skills_config has %d skills", len(skills))

            # Get sandbox config settings
            sandbox_pip_packages = None
            sandbox_timeout = 3600  # Default 1 hour
            if cfg.sandbox_config:
                sandbox_pip_packages = cfg.sandbox_config.pip_packages
                sandbox_timeout = cfg.sandbox_config.timeout_seconds or 3600

            # Create the file attachment nodes (two-node pattern for progressive UI)
            emit_status_node, file_attachment_node = create_file_attachment_nodes(
                thread_id=thread_id,
                langconnect_url=langconnect_api_url,
                access_token=supabase_token,
                skills=skills,
                sandbox_pip_packages=sandbox_pip_packages,
                sandbox_timeout=sandbox_timeout,
            )
            file_attachment_processor = (emit_status_node, file_attachment_node)

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
        logger.debug("[TOOLS_AGENT] message_trimming_enabled max_tokens=%s", model_info.trimming_max_tokens)

    # Step 5c: Create image preprocessor for handling image storage paths
    # Get LangConnect URL from config
    langconnect_api_url = (
        cfg.rag.langconnect_api_url if cfg.rag else "http://langconnect:8080"
    )

    # Create image preprocessor
    image_hook = create_image_preprocessor(langconnect_api_url)

    # Combine hooks: ORPHAN RESOLUTION first, then TRIMMING, then IMAGE PROCESSING
    # Order rationale:
    # 1. Resolve orphans first (sanitize invalid message sequences from cancelled tool calls)
    # 2. Trim (based on small storage path tokens, not massive base64 data)
    # 3. Convert images to signed URLs (or base64 in local dev)
    orphan_hook = create_orphan_resolution_hook()

    combined_hook = None
    if trimming_hook and image_hook:
        async def combined_pre_model_hook(state, config):
            # 1. Resolve orphaned tool calls first
            state = {**state, **orphan_hook(state)}
            # 2. Trim (when images are just storage paths ~50 tokens each)
            state = {**state, **trimming_hook(state)}
            # 3. Then convert images to signed URLs (or base64 in local dev)
            state = await image_hook(state, config)
            return state
        combined_hook = combined_pre_model_hook
    elif image_hook:
        async def combined_pre_model_hook(state, config):
            state = {**state, **orphan_hook(state)}
            state = await image_hook(state, config)
            return state
        combined_hook = combined_pre_model_hook
    elif trimming_hook:
        def combined_pre_model_hook(state):
            state = {**state, **orphan_hook(state)}
            state = {**state, **trimming_hook(state)}
            return state
        combined_hook = combined_pre_model_hook
    else:
        combined_hook = orphan_hook

    # Step 6: Collect tool approvals from configuration
    # Merge approvals from both MCP and RAG sources
    mcp_approvals = cfg.mcp_config.tool_approvals if cfg.mcp_config else {}
    rag_approvals = cfg.rag.tool_approvals if cfg.rag else {}
    tool_approvals = merge_tool_approvals(mcp_approvals, rag_approvals)

    # Step 7: Create and return the ReAct agent with approval support
    # Get recursion limit from config, default to DEFAULT_RECURSION_LIMIT if not specified
    recursion_limit = cfg.recursion_limit if cfg.recursion_limit is not None else DEFAULT_RECURSION_LIMIT

    # Build the system prompt using the two-layer structure
    # When sandbox_enabled, includes execution context (role, sandbox, skills)
    # When sandbox_disabled, just includes role and domain instructions
    skills_for_prompt = None
    if cfg.sandbox_enabled and cfg.skills_config and cfg.skills_config.skills:
        skills_for_prompt = [
            {"name": s.name, "description": s.description}
            for s in cfg.skills_config.skills
            if s.name
        ]

    final_prompt = build_system_prompt(
        user_prompt=cfg.system_prompt,
        sandbox_enabled=cfg.sandbox_enabled,
        skills=skills_for_prompt,
    )

    # Determine state schema based on sandbox mode
    state_schema = ToolsAgentState if cfg.sandbox_enabled else None

    logger.debug("[TOOLS_AGENT] agent_created tools_count=%s sandbox=%s", len(tools), cfg.sandbox_enabled)

    return create_react_agent_with_approval(
        prompt=final_prompt,
        model=model,
        tools=tools,
        tool_approvals=tool_approvals,
        config_schema=GraphConfigPydantic,
        pre_model_hook=combined_hook,  # Combined image + trimming hooks
        state_schema=state_schema,
        file_attachment_processor=file_attachment_processor,
    ).with_config({"recursion_limit": recursion_limit})
