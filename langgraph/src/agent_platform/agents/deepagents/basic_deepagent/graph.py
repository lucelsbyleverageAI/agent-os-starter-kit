import json
from langchain_core.runnables import RunnableConfig
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from dotenv import find_dotenv, load_dotenv
import logging

load_dotenv(find_dotenv())

from agent_platform.services.mcp_token import fetch_tokens
from agent_platform.utils.tool_utils import (
    create_rag_tool_with_universal_context,
    create_langchain_mcp_tool_with_universal_context,
    create_collection_tools,
)
from agent_platform.utils.model_utils import (
    init_model,
    ModelConfig,
    RetryConfig,
)
from agent_platform.agents.deepagents.basic_deepagent.configuration import (
    GraphConfigPydantic,
)
from agent_platform.agents.deepagents.graph import async_create_deep_agent
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


async def graph(config: RunnableConfig):
    # Standard logging via Sentry integration; no verbosity overrides
    raw_config = config.get("configurable", {})

    # Map UI field names to Pydantic field names
    # The UI sends fields with title case and spaces, but Pydantic expects snake_case
    if 'Include General-Purpose Agent' in raw_config:
        raw_config['include_general_purpose_agent'] = raw_config['Include General-Purpose Agent']

    cfg = GraphConfigPydantic(**raw_config)

    tools = []

    supabase_token = config.get("configurable", {}).get(
        "x-supabase-access-token"
    ) or config.get("metadata", {}).get("supabaseAccessToken")

    # Add collection tools (RAG + file system) if configured
    if cfg.rag and cfg.rag.langconnect_api_url and cfg.rag.collections and supabase_token:
        try:
            # Get enabled tools list (default to hybrid_search only for backward compatibility)
            enabled_tools = getattr(cfg.rag, "enabled_tools", None) or ["hybrid_search"]
            
            # Create all enabled tools using the new orchestrator function
            collection_tools = await create_collection_tools(
                langconnect_api_url=cfg.rag.langconnect_api_url,
                collection_ids=cfg.rag.collections,
                enabled_tools=enabled_tools,
                access_token=supabase_token,
                config_getter=lambda: config,
            )
            tools.extend(collection_tools)
        except Exception:
            logger.exception("[basic_deepagent] Failed to create collection tools")

    if (
        cfg.mcp_config
        and cfg.mcp_config.url
        and (mcp_auth_data := await fetch_tokens(config))
    ):
        # If no tools were selected, do not add any MCP tools
        tool_names_to_find = set(cfg.mcp_config.tools or [])
        if tool_names_to_find:
            server_url = cfg.mcp_config.url.rstrip("/") + "/mcp"
            headers = {}
            auth_type = mcp_auth_data.get("auth_type")
            if auth_type == "mcp_access_token":
                access_token = mcp_auth_data.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            elif auth_type == "supabase_jwt":
                # Legacy fallback (should not be used now)
                jwt_token = mcp_auth_data.get("jwt_token")
                if jwt_token:
                    headers["Authorization"] = f"Bearer {jwt_token}"
            elif auth_type == "service_account":
                access_token = mcp_auth_data.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"

            fetched_mcp_tools_list = []
            names_of_tools_added = set()

            try:
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
                                # Only add tools that are specifically requested
                                if (
                                    mcp_tool.name in tool_names_to_find
                                    and mcp_tool.name not in names_of_tools_added
                                ):
                                    wrapped_tool = (
                                        create_langchain_mcp_tool_with_universal_context(
                                            mcp_tool, server_url, mcp_auth_data, lambda: config
                                        )
                                    )
                                    fetched_mcp_tools_list.append(wrapped_tool)
                                    names_of_tools_added.add(mcp_tool.name)
                            page_cursor = getattr(tool_list_page, "nextCursor", None)
                            if not page_cursor:
                                break
                            if len(names_of_tools_added) == len(tool_names_to_find):
                                break
                        tools.extend(fetched_mcp_tools_list)
            except Exception:
                logger.exception(
                    "[basic_deepagent] MCP connection/tool loading error"
                )

    # Initialize model with centralized config using init_model_simple
    # This ensures we get the correct max_tokens from the model registry
    from agent_platform.utils.model_utils import init_model_simple
    model = init_model_simple(model_name=cfg.model_name)

    sub_agents_config = json.loads(cfg.json()).get("sub_agents", [])

    # Register the full schema so the UI renders all fields/tabs
    agent = async_create_deep_agent(
        tools=tools,
        instructions=cfg.system_prompt,
        model=model,
        subagents=sub_agents_config,
        config_schema=GraphConfigPydantic,
        runnable_config=config,
        include_general_purpose_agent=cfg.include_general_purpose_agent,
    )

    return agent