"""Sub-agent module for Skills DeepAgent.

This is a modified version of deepagents/sub_agent.py that:
1. Uses SkillsDeepAgentState instead of DeepAgentState
2. Includes execute_in_sandbox tool for all sub-agents
3. Uses only write_todos as the built-in tool (no state file tools)
4. Has a condensed task tool description
"""

try:
    from .state import SkillsDeepAgentState, Todo
    from .toolkit import write_todos
    from .subagent_prompts import build_subagent_system_prompt
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import SkillsDeepAgentState, Todo
    from agent_platform.agents.deepagents.skills_deepagent.toolkit import write_todos
    from agent_platform.agents.deepagents.skills_deepagent.subagent_prompts import build_subagent_system_prompt

from agent_platform.services.mcp_token import fetch_tokens
from agent_platform.utils.tool_utils import (
    create_collection_tools,
    create_langchain_mcp_tool_with_universal_context,
)
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from agent_platform.agents.deepagents.builder import SerializableSubAgent, RagConfig, MCPConfig
from agent_platform.agents.deepagents.custom_react_agent import custom_create_react_agent
from langchain_core.tools import BaseTool
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage, HumanMessage
from langchain_core.language_models import LanguageModelLike
from typing import Annotated, Optional, Callable, List, Union
from agent_platform.utils.model_utils import (
    init_model_simple,
    get_model_info,
    MessageTrimmingConfig,
    create_trimming_hook,
)
from agent_platform.utils.message_utils import create_image_preprocessor
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


# Condensed task description (~400 tokens instead of ~800)
TASK_DESCRIPTION_PREFIX = """Delegate tasks to specialized sub-agents.

Available agents:
- general-purpose: Handles research, analysis, and multi-step tasks
{other_agents}
"""

TASK_DESCRIPTION_SUFFIX = """
**Usage**: Specify `subagent_type` to select which agent.

**Guidelines**:
- Sub-agents are stateless - provide complete context in your prompt
- They return a single response with their findings
- Tell them exactly what to do and what to return
- They share the sandbox filesystem at /sandbox/

**Do NOT use** for simple file reads or single operations you can do directly.
"""

# Default prompt for the general-purpose sub-agent
GENERAL_PURPOSE_SUBAGENT_PROMPT = """You are a general-purpose sub-agent with access to tools. You have been given a task by the main agent. Complete the task using the tools available to you. Always summarise your work in your final response, referencing any created files."""

# Tools that should only be available to the main agent, not sub-agents
MAIN_AGENT_ONLY_TOOLS = {"publish_file_to_user"}


async def _get_tools_for_sub_agent(
    sub_agent_config: Union[SerializableSubAgent, dict],
    parent_tools: List[BaseTool],
    config: RunnableConfig,
) -> List[BaseTool]:
    """Get tools specific to a sub-agent (RAG and MCP tools)."""
    tools = []
    tools_by_name = {t.name: t for t in parent_tools}

    # Handle both dictionary (from frontend JSON) and object formats
    if isinstance(sub_agent_config, dict):
        agent_tools = sub_agent_config.get('tools', [])
        rag_config = sub_agent_config.get('rag_config', {})
        mcp_config = sub_agent_config.get('mcp_config', {})
    else:
        agent_tools = getattr(sub_agent_config, 'tools', [])
        rag_config = getattr(sub_agent_config, 'rag_config', None)
        mcp_config = getattr(sub_agent_config, 'mcp_config', None)

    if agent_tools:
        for tool_name in agent_tools:
            if tool_name in tools_by_name:
                tools.append(tools_by_name[tool_name])

    supabase_token = config.get("configurable", {}).get(
        "x-supabase-access-token"
    ) or config.get("metadata", {}).get("supabaseAccessToken")

    # Handle RAG config
    if rag_config:
        if isinstance(rag_config, dict):
            langconnect_api_url = rag_config.get('langconnect_api_url')
            collections = rag_config.get('collections', [])
            enabled_tools = rag_config.get('enabled_tools', ["collection_hybrid_search"])
        else:
            langconnect_api_url = getattr(rag_config, 'langconnect_api_url', None)
            collections = getattr(rag_config, 'collections', [])
            enabled_tools = getattr(rag_config, 'enabled_tools', ["collection_hybrid_search"])

        if not langconnect_api_url:
            langconnect_api_url = (
                config.get("configurable", {})
                .get("rag", {})
                .get("langconnect_api_url")
            )

        if langconnect_api_url and collections and supabase_token:
            try:
                collection_tools = await create_collection_tools(
                    langconnect_api_url=langconnect_api_url,
                    collection_ids=collections,
                    enabled_tools=enabled_tools,
                    access_token=supabase_token,
                    config_getter=lambda: config,
                )
                tools.extend(collection_tools)
                logger.info("[SKILLS_SUB_AGENT] collection_tools_loaded count=%s", len(collection_tools))
            except Exception as e:
                logger.exception("[SKILLS_SUB_AGENT] collection_tools_create_failed error=%s", str(e))

    # Handle MCP config
    if mcp_config:
        if isinstance(mcp_config, dict):
            mcp_url = mcp_config.get('url')
            mcp_tools = mcp_config.get('tools', [])
        else:
            mcp_url = getattr(mcp_config, 'url', None)
            mcp_tools = getattr(mcp_config, 'tools', [])

        if not mcp_url:
            mcp_url = (
                config.get("configurable", {})
                .get("mcp_config", {})
                .get("url")
            )

        if mcp_url and (mcp_auth_data := await fetch_tokens(config)):
            server_url = mcp_url.rstrip("/") + "/mcp"
            headers = {}
            auth_type = mcp_auth_data.get("auth_type")
            if auth_type in ("mcp_access_token", "oauth", "service_account"):
                access_token = mcp_auth_data.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            elif auth_type == "supabase_jwt":
                jwt_token = mcp_auth_data.get("jwt_token")
                if jwt_token:
                    headers["Authorization"] = f"Bearer {jwt_token}"

            tool_names_to_find = set(mcp_tools or [])
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
                                    tool_names_to_find and
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
                            page_cursor = getattr(tool_list_page, 'nextCursor', None)
                            if not page_cursor:
                                break
                            if tool_names_to_find and len(names_of_tools_added) == len(tool_names_to_find):
                                break
                        tools.extend(fetched_mcp_tools_list)
                        logger.info("[SKILLS_SUB_AGENT] mcp_tools_added count=%s", len(fetched_mcp_tools_list))
            except Exception:
                logger.exception("[SKILLS_SUB_AGENT] error_fetching_mcp_tools")

    return tools


def _create_combined_hook(trimming_hook: Optional[Callable], img_preprocessor: Optional[Callable]) -> Optional[Callable]:
    """Factory function to properly capture hook instances in closure."""
    if trimming_hook and img_preprocessor:
        async def combined_hook(state, config):
            trimming_result = trimming_hook(state)
            state = {**state, **trimming_result}
            state = await img_preprocessor(state, config)
            return state
        return combined_hook
    elif img_preprocessor:
        return img_preprocessor
    elif trimming_hook:
        def wrapped_trimming_hook(state, config):
            return trimming_hook(state)
        return wrapped_trimming_hook
    return None


async def _get_agents(
    tools: List[BaseTool],
    instructions: str,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
    main_agent_skills: Optional[List[dict]] = None,
):
    """Build sub-agent instances for skills deepagent.

    Key differences from base deepagent:
    - Only write_todos as built-in tool (no state file tools)
    - execute_in_sandbox tool comes from `tools` param (passed from main agent)
    - Uses SkillsDeepAgentState
    """
    # Only write_todos as built-in - sandbox tool comes from `tools` param
    all_builtin_tools = [write_todos]
    agents = {}

    # Filter out main-agent-only tools for sub-agents
    subagent_tools = [t for t in tools if getattr(t, "name", "") not in MAIN_AGENT_ONLY_TOOLS]

    # Get LangConnect URL from config
    langconnect_api_url = "http://langconnect:8080"
    if config:
        rag_config = config.get("configurable", {}).get("rag", {})
        if isinstance(rag_config, dict):
            langconnect_api_url = rag_config.get("langconnect_api_url", langconnect_api_url)

    # Create image preprocessor (shared by all sub-agents)
    image_preprocessor = create_image_preprocessor(langconnect_api_url)

    # Only add general-purpose agent if enabled
    if include_general_purpose:
        gp_model_name = model if isinstance(model, str) else "anthropic/claude-sonnet-4"
        gp_model_info = get_model_info(gp_model_name)
        gp_trimming_hook = None

        if gp_model_info.enable_trimming:
            gp_trimming_hook = create_trimming_hook(
                MessageTrimmingConfig(
                    enabled=True,
                    max_tokens=gp_model_info.trimming_max_tokens,
                    strategy="last",
                    start_on="human",
                    end_on=("human", "tool"),
                    include_system=True,
                )
            )
            logger.info("[SKILLS_SUB_AGENT] trimming_enabled agent=general-purpose max_tokens=%s",
                       gp_model_info.trimming_max_tokens)

        gp_combined_hook = _create_combined_hook(gp_trimming_hook, image_preprocessor)

        # Build enhanced prompt for general-purpose agent
        # General-purpose agent inherits the main agent's skills
        gp_enhanced_prompt = build_subagent_system_prompt(GENERAL_PURPOSE_SUBAGENT_PROMPT, skills=main_agent_skills)
        gp_skills_count = len(main_agent_skills) if main_agent_skills else 0
        logger.info("[SKILLS_SUB_AGENT] prompt_enhanced agent=general-purpose skills_count=%s", gp_skills_count)

        # Include tools from parent (which includes execute_in_sandbox)
        # Use subagent_tools to exclude main-agent-only tools like publish_file_to_user
        gp_tools = list(all_builtin_tools) + list(subagent_tools)

        agents["general-purpose"] = custom_create_react_agent(
            model,
            prompt=gp_enhanced_prompt,
            tools=gp_tools,
            state_schema=state_schema,
            checkpointer=False,
            post_model_hook=post_model_hook,
            pre_model_hook=gp_combined_hook,
            enable_image_processing=False
        )

    # Built-in tools that every agent should have
    builtin_tools_by_name = {
        t.name: t for t in all_builtin_tools
    }

    for _agent in subagents:
        # Handle both dictionary (from frontend JSON) and object formats
        if isinstance(_agent, dict):
            agent_name = _agent.get('name', 'unnamed_agent')
            agent_tools = _agent.get('tools', [])
            agent_model = _agent.get('model_name', None) or _agent.get('model', None)
            agent_prompt = _agent.get('prompt', 'You are a helpful assistant.')
            agent_skills_config = _agent.get('skills_config')
        else:
            agent_name = getattr(_agent, 'name', 'unnamed_agent')
            agent_tools = getattr(_agent, 'tools', [])
            agent_model = getattr(_agent, 'model_name', None) or getattr(_agent, 'model', None)
            agent_prompt = getattr(_agent, 'prompt', 'You are a helpful assistant.')
            agent_skills_config = getattr(_agent, 'skills_config', None)

        logger.info("[SKILLS_SUB_AGENT] config_extraction agent=%s skills_config=%s",
                   agent_name, agent_skills_config is not None)

        # Convert skills_config to list of skills for prompt building
        agent_skills = []
        if agent_skills_config:
            if isinstance(agent_skills_config, dict):
                agent_skills = agent_skills_config.get('skills', [])
            else:
                agent_skills = getattr(agent_skills_config, 'skills', [])

        if config:
            # Fetch sub-agent specific tools (RAG/MCP)
            sub_specific_tools = await _get_tools_for_sub_agent(
                _agent, list(builtin_tools_by_name.values()), config
            )
            # Combine: built-ins + parent tools (execute_in_sandbox) + sub-agent specific
            # Use subagent_tools to exclude main-agent-only tools like publish_file_to_user
            combined_tools_by_name = {}
            for tool_obj in sub_specific_tools + list(builtin_tools_by_name.values()) + list(subagent_tools):
                combined_tools_by_name[getattr(tool_obj, "name", str(tool_obj))] = tool_obj
            _tools = list(combined_tools_by_name.values())
            logger.info("[SKILLS_SUB_AGENT] tools_composition agent=%s total=%s",
                       agent_name, len(_tools))
        else:
            # Use subagent_tools to exclude main-agent-only tools like publish_file_to_user
            _tools = list(builtin_tools_by_name.values()) + list(subagent_tools)

        if agent_model:
            if isinstance(agent_model, str):
                sub_model = init_model_simple(model_name=agent_model)
                logger.info("[SKILLS_SUB_AGENT] model_initialized agent=%s model=%s", agent_name, agent_model)
            elif isinstance(agent_model, dict):
                model_name = agent_model.get('model_name') or agent_model.get('model')
                sub_model = init_model_simple(model_name=model_name)
                logger.info("[SKILLS_SUB_AGENT] model_initialized agent=%s model=%s", agent_name, model_name)
            else:
                sub_model = agent_model
        else:
            sub_model = model
            logger.info("[SKILLS_SUB_AGENT] model_initialized agent=%s source=parent", agent_name)

        # Create trimming hook for this sub-agent
        sub_model_name = None
        if isinstance(agent_model, str):
            sub_model_name = agent_model
        elif isinstance(agent_model, dict):
            sub_model_name = agent_model.get('model_name') or agent_model.get('model')
        if not sub_model_name:
            sub_model_name = model if isinstance(model, str) else "anthropic/claude-sonnet-4"

        sub_model_info = get_model_info(sub_model_name)
        sub_trimming_hook = None

        if sub_model_info.enable_trimming:
            sub_trimming_hook = create_trimming_hook(
                MessageTrimmingConfig(
                    enabled=True,
                    max_tokens=sub_model_info.trimming_max_tokens,
                    strategy="last",
                    start_on="human",
                    end_on=("human", "tool"),
                    include_system=True,
                )
            )
            logger.info("[SKILLS_SUB_AGENT] trimming_enabled agent=%s max_tokens=%s",
                       agent_name, sub_model_info.trimming_max_tokens)

        sub_combined_hook = _create_combined_hook(sub_trimming_hook, image_preprocessor)

        # Build enhanced system prompt with sub-agent context and skills
        enhanced_prompt = build_subagent_system_prompt(agent_prompt, agent_skills)
        logger.info("[SKILLS_SUB_AGENT] prompt_enhanced agent=%s skills_count=%s",
                   agent_name, len(agent_skills))

        agents[agent_name] = custom_create_react_agent(
            sub_model,
            prompt=enhanced_prompt,
            tools=_tools,
            state_schema=state_schema,
            checkpointer=False,
            post_model_hook=post_model_hook,
            pre_model_hook=sub_combined_hook,
            enable_image_processing=False,
        )

    return agents


def _get_subagent_description(subagents):
    """Build list of sub-agent descriptions for task tool."""
    descriptions = []
    for _agent in subagents:
        if isinstance(_agent, dict):
            name = _agent.get('name', 'Unnamed Agent')
            description = _agent.get('description', 'No description')
        else:
            name = getattr(_agent, 'name', 'Unnamed Agent')
            description = getattr(_agent, 'description', 'No description')
        descriptions.append(f"- {name}: {description}")
    return descriptions


def _create_task_tool(
    tools: List[BaseTool],
    instructions: str,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
    main_agent_skills: Optional[List[dict]] = None,
):
    """Create async task tool for delegating to sub-agents."""
    other_agents_string = _get_subagent_description(subagents)

    # Build description conditionally
    if not include_general_purpose and not other_agents_string:
        task_description = """Delegate tasks to sub-agents.

Note: No sub-agents are currently configured. Add custom sub-agents in agent configuration.
""" + TASK_DESCRIPTION_SUFFIX
    elif include_general_purpose:
        task_description = TASK_DESCRIPTION_PREFIX.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX
    else:
        task_description_no_gp = """Delegate tasks to specialized sub-agents.

Available agents:
{other_agents}
"""
        task_description = task_description_no_gp.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX

    @tool(description=task_description)
    async def task(
        description: str,
        subagent_type: str,
        state: Annotated[SkillsDeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        agents = await _get_agents(
            tools,
            instructions,
            subagents,
            model,
            state_schema,
            post_model_hook,
            config,
            include_general_purpose,
            main_agent_skills,
        )
        if subagent_type not in agents:
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
        sub_agent = agents[subagent_type]
        # Create a new state dict for the sub-agent invocation
        sub_agent_state = state.copy()
        sub_agent_state["messages"] = [HumanMessage(content=description)]
        # Pass config so sub-agent can access run_id for cost tracking
        result = await sub_agent.ainvoke(sub_agent_state, config)
        return Command(
            update={
                # Note: No "files" update - skills_deepagent doesn't use state files
                "messages": [
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task


def _create_sync_task_tool(
    tools: List[BaseTool],
    instructions: str,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
    main_agent_skills: Optional[List[dict]] = None,
):
    """Create sync task tool for delegating to sub-agents."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        agents = asyncio.run(
            _get_agents(
                tools, instructions, subagents, model, state_schema,
                post_model_hook, config, include_general_purpose, main_agent_skills,
            )
        )
    else:
        agents = asyncio.run(
            _get_agents(
                tools, instructions, subagents, model, state_schema,
                post_model_hook, config, include_general_purpose, main_agent_skills,
            )
        )

    other_agents_string = _get_subagent_description(subagents)

    # Build description conditionally
    if not include_general_purpose and not other_agents_string:
        task_description = """Delegate tasks to sub-agents.

Note: No sub-agents are currently configured. Add custom sub-agents in agent configuration.
""" + TASK_DESCRIPTION_SUFFIX
    elif include_general_purpose:
        task_description = TASK_DESCRIPTION_PREFIX.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX
    else:
        task_description_no_gp = """Delegate tasks to specialized sub-agents.

Available agents:
{other_agents}
"""
        task_description = task_description_no_gp.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX

    @tool(description=task_description)
    def task(
        description: str,
        subagent_type: str,
        state: Annotated[SkillsDeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        if subagent_type not in agents:
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
        sub_agent = agents[subagent_type]
        sub_agent_state = state.copy()
        sub_agent_state["messages"] = [HumanMessage(content=description)]
        # Pass config so sub-agent can access run_id for cost tracking
        result = sub_agent.invoke(sub_agent_state, config)
        return Command(
            update={
                # Note: No "files" update - skills_deepagent doesn't use state files
                "messages": [
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task
