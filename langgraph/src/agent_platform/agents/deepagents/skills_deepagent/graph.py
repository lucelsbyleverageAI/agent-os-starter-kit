"""
Skills DeepAgent graph definition.

This module defines the main graph for the Skills DeepAgent, which uses:
- E2B sandbox for ALL file operations (no state filesystem)
- Two sandbox tools: run_code (for writing files) and run_command (for shell ops)
- Local agent_builder instead of base deepagent graph

This is a refactored version that creates an independent skills agent implementation
while keeping the base deepagent backward compatible.
"""

import json
from dotenv import find_dotenv, load_dotenv

from langchain_core.runnables import RunnableConfig
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

load_dotenv(find_dotenv())

from agent_platform.services.mcp_token import fetch_tokens
from agent_platform.utils.tool_utils import (
    create_langchain_mcp_tool_with_universal_context,
    create_collection_tools,
)
from agent_platform.utils.model_utils import (
    init_model_simple,
    get_model_info,
    MessageTrimmingConfig,
    create_trimming_hook,
)
from agent_platform.sentry import get_logger

# Import from local skills_deepagent modules (NOT base deepagents)
# Using try/except pattern to support both direct execution and package imports
try:
    from .configuration import GraphConfigPydantic
    from .prompts import build_system_prompt
    from .sandbox_tools import get_or_create_sandbox, create_sandbox_tools
    from .agent_builder import async_create_skills_agent
    from .tools import create_publish_file_tool
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.configuration import GraphConfigPydantic
    from agent_platform.agents.deepagents.skills_deepagent.prompts import build_system_prompt
    from agent_platform.agents.deepagents.skills_deepagent.sandbox_tools import get_or_create_sandbox, create_sandbox_tools
    from agent_platform.agents.deepagents.skills_deepagent.agent_builder import async_create_skills_agent
    from agent_platform.agents.deepagents.skills_deepagent.tools import create_publish_file_tool

logger = get_logger(__name__)


async def graph(config: RunnableConfig):
    """
    Build Skills DeepAgent graph.

    This creates an agent with:
    - E2B sandbox for ALL file operations (sandbox-only, no state filesystem)
    - Two sandbox tools: run_code (writing files, complex ops) and run_command (shell ops)
    - Skills support with automatic loading and system prompt integration
    - Sub-agent support with per-agent skills allocation (sub-agents also get sandbox access)
    """
    raw_config = config.get("configurable", {})

    # Map UI field names to Pydantic field names
    if 'Include General-Purpose Agent' in raw_config:
        raw_config['include_general_purpose_agent'] = raw_config['Include General-Purpose Agent']

    cfg = GraphConfigPydantic(**raw_config)

    tools = []

    # Get authentication tokens
    supabase_token = config.get("configurable", {}).get(
        "x-supabase-access-token"
    ) or config.get("metadata", {}).get("supabaseAccessToken")

    thread_id = config.get("configurable", {}).get("thread_id", "default")

    # Get user_id from metadata (set by auth system)
    user_id = config.get("metadata", {}).get("owner", "")

    # Get LangConnect URL
    langconnect_url = "http://langconnect:8080"
    if cfg.rag and cfg.rag.langconnect_api_url:
        langconnect_url = cfg.rag.langconnect_api_url

    # Extract skills from config
    skills = []
    if cfg.skills_config and cfg.skills_config.skills:
        skills = [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
            }
            for s in cfg.skills_config.skills
        ]

    # Get sandbox configuration
    sandbox_timeout = 600
    sandbox_pip_packages = []
    if cfg.sandbox_config:
        sandbox_timeout = cfg.sandbox_config.timeout_seconds
        sandbox_pip_packages = cfg.sandbox_config.pip_packages

    # ALWAYS initialize sandbox for skills_deepagent (it's the core of this agent type)
    # The sandbox is required for all file operations
    try:
        await get_or_create_sandbox(
            thread_id=thread_id,
            skills=skills,
            langconnect_url=langconnect_url,
            access_token=supabase_token,
            pip_packages=sandbox_pip_packages,
            timeout=sandbox_timeout
        )
        # Add both sandbox tools: run_code and run_command
        run_code_tool, run_command_tool = create_sandbox_tools(thread_id)
        tools.append(run_code_tool)
        tools.append(run_command_tool)

        # Add publish_file_to_user tool for agent-to-user file sharing
        if user_id and supabase_token:
            publish_tool = create_publish_file_tool(
                thread_id=thread_id,
                user_id=user_id,
                langconnect_url=langconnect_url,
                access_token=supabase_token,
            )
            tools.append(publish_tool)
            logger.info("[SKILLS_DEEPAGENT] Added publish_file_to_user tool")
        else:
            logger.warning("[SKILLS_DEEPAGENT] publish_file_to_user tool not added: missing user_id or token")

        logger.info(f"[SKILLS_DEEPAGENT] Initialized sandbox with {len(skills)} skills")
    except Exception as e:
        logger.error(f"[SKILLS_DEEPAGENT] Failed to initialize sandbox: {e}")
        # For skills_deepagent, sandbox is required - raise the error
        raise RuntimeError(f"Sandbox initialization failed: {e}. Sandbox is required for skills_deepagent.")

    # Note: write_todos is added by agent_builder, not here

    # Add collection tools (RAG + file system) if configured
    if cfg.rag and cfg.rag.langconnect_api_url and cfg.rag.collections and supabase_token:
        try:
            enabled_tools = getattr(cfg.rag, "enabled_tools", None) or ["hybrid_search"]

            collection_tools = await create_collection_tools(
                langconnect_api_url=cfg.rag.langconnect_api_url,
                collection_ids=cfg.rag.collections,
                enabled_tools=enabled_tools,
                access_token=supabase_token,
                config_getter=lambda: config,
            )
            tools.extend(collection_tools)
        except Exception:
            logger.exception("[skills_deepagent] Failed to create collection tools")

    # Add MCP tools if configured
    if (
        cfg.mcp_config
        and cfg.mcp_config.url
        and (mcp_auth_data := await fetch_tokens(config))
    ):
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
                logger.exception("[skills_deepagent] MCP connection/tool loading error")

    # Initialize model
    model = init_model_simple(model_name=cfg.model_name)

    # Create message trimming hook based on model-level settings
    model_info = get_model_info(cfg.model_name)
    trimming_hook = None

    if model_info.enable_trimming:
        trimming_hook = create_trimming_hook(
            MessageTrimmingConfig(
                enabled=True,
                max_tokens=model_info.trimming_max_tokens,
                strategy="last",
                start_on="human",
                end_on=("human", "tool"),
                include_system=True,
            )
        )
        logger.info(
            "[SKILLS_DEEPAGENT] message_trimming_enabled max_tokens=%s (model: %s)",
            model_info.trimming_max_tokens,
            model_info.display_name
        )
    else:
        logger.info(
            "[SKILLS_DEEPAGENT] message_trimming_disabled (model: %s)",
            model_info.display_name
        )

    # Prepare sub-agents config
    sub_agents_config = json.loads(cfg.model_dump_json()).get("sub_agents", [])

    # Determine if sub-agents are available (for prompt building)
    has_subagents = (sub_agents_config and len(sub_agents_config) > 0) or cfg.include_general_purpose_agent

    # Build system prompt with skills table and proper tool section
    system_prompt = build_system_prompt(
        user_prompt=cfg.system_prompt,
        skills=skills,
        has_subagents=has_subagents
    )

    # Create the skills agent using local agent_builder
    # This uses SkillsDeepAgentState (no files field) and write_todos + run_code + run_command
    agent = async_create_skills_agent(
        tools=tools,  # Contains run_code, run_command + RAG + MCP tools
        instructions=system_prompt,
        model=model,
        subagents=sub_agents_config,
        config_schema=GraphConfigPydantic,
        runnable_config=config,
        include_general_purpose_agent=cfg.include_general_purpose_agent,
        pre_model_hook=trimming_hook,
        # File attachment processing parameters
        thread_id=thread_id,
        langconnect_url=langconnect_url,
        access_token=supabase_token,
    )

    return agent
