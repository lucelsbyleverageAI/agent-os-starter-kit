try:
    from .deep_agent_toolkit_descriptions import TASK_DESCRIPTION_PREFIX, TASK_DESCRIPTION_SUFFIX
    from .state import DeepAgentState
    from .deep_agent_toolkit import write_todos, write_file, read_file, ls, edit_file
except ImportError:
    from agent_platform.agents.deepagents.deep_agent_toolkit_descriptions import TASK_DESCRIPTION_PREFIX, TASK_DESCRIPTION_SUFFIX
    from agent_platform.agents.deepagents.state import DeepAgentState
    from agent_platform.agents.deepagents.deep_agent_toolkit import write_todos, write_file, read_file, ls, edit_file
from agent_platform.services.mcp_token import fetch_tokens
from agent_platform.utils.tool_utils import (
    create_collection_tools,
    create_langchain_mcp_tool_with_universal_context,
)
from agent_platform.utils.prompt_utils import append_datetime_to_prompt
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from .builder import SerializableSubAgent, RagConfig, MCPConfig
from langgraph.prebuilt import create_react_agent
from .custom_react_agent import custom_create_react_agent
from langchain_core.tools import BaseTool
from typing_extensions import TypedDict
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_core.language_models import LanguageModelLike
from typing import Annotated, NotRequired, Any, Union, Optional, Callable, List
from agent_platform.utils.model_utils import (
    init_model,
    ModelConfig,
    RetryConfig,
    get_model_info,
    MessageTrimmingConfig,
    create_trimming_hook,
)
from agent_platform.utils.message_utils import create_image_preprocessor
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger
logger = get_logger(__name__)

# Default prompt for the general-purpose sub-agent
GENERAL_PURPOSE_SUBAGENT_PROMPT = """You are a sub-agent with access to a variety of tools. You have been given a task by your supervisor. Please complete the task based on their instructions using the tools available to you if and when needed. Always produce your result as a file using the write_file tool and summarise your work in your final response, referencing any created or updated files. Do not ask for clarifications from the main agent unless absolutely necessary, try to do the task with the information provided."""


async def _get_tools_for_sub_agent(
    sub_agent_config: Union[SerializableSubAgent, dict],
    parent_tools: List[BaseTool],
    config: RunnableConfig,
) -> List[BaseTool]:
    tools = []
    tools_by_name = {t.name: t for t in parent_tools}

    # Handle both dictionary (from frontend JSON) and object formats
    if isinstance(sub_agent_config, dict):
        agent_tools = sub_agent_config.get('tools', [])
        rag_config = sub_agent_config.get('rag_config', {})
        mcp_config = sub_agent_config.get('mcp_config', {})
    else:
        # Handle SerializableSubAgent object
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

    # Handle RAG config (fallback to global RAG URL if not provided per sub-agent)
    if rag_config:
        if isinstance(rag_config, dict):
            langconnect_api_url = rag_config.get('langconnect_api_url')
            collections = rag_config.get('collections', [])
            enabled_tools = rag_config.get('enabled_tools', ["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_grep_files"])
        else:
            langconnect_api_url = getattr(rag_config, 'langconnect_api_url', None)
            collections = getattr(rag_config, 'collections', [])
            enabled_tools = getattr(rag_config, 'enabled_tools', ["collection_hybrid_search", "collection_list", "collection_list_files", "collection_read_file", "collection_grep_files"])
        
        # Fallback to global RAG URL from main config
        if not langconnect_api_url:
            langconnect_api_url = (
                config.get("configurable", {})
                .get("rag", {})
                .get("langconnect_api_url")
            )
        
        if langconnect_api_url and collections and supabase_token:
            try:
                # Use the new create_collection_tools that supports all file system operations
                collection_tools = await create_collection_tools(
                    langconnect_api_url=langconnect_api_url,
                    collection_ids=collections,
                    enabled_tools=enabled_tools,
                    access_token=supabase_token,
                    config_getter=lambda: config,
                )
                tools.extend(collection_tools)
                logger.info("[SUB_AGENT] collection_tools_loaded count=%s enabled_tools=%s", 
                           len(collection_tools), enabled_tools)
            except Exception as e:
                logger.exception("[SUB_AGENT] collection_tools_create_failed error=%s", str(e))
                pass

    # Handle MCP config (fallback to global MCP URL if not provided per sub-agent)
    if mcp_config:
        if isinstance(mcp_config, dict):
            mcp_url = mcp_config.get('url')
            mcp_tools = mcp_config.get('tools', [])
        else:
            mcp_url = getattr(mcp_config, 'url', None)
            mcp_tools = getattr(mcp_config, 'tools', [])
        # Fallback to global MCP URL from main config
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
            if auth_type == "mcp_access_token":
                access_token = mcp_auth_data.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            elif auth_type == "oauth":
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

            tool_names_to_find = set(mcp_tools or [])
            fetched_mcp_tools_list = []
            names_of_tools_added = set()
            
            logger.info("[SUB_AGENT] mcp_tools_filtering start")
            logger.debug("[SUB_AGENT] requested_tools=%s", tool_names_to_find)
            logger.debug("[SUB_AGENT] mcp_url=%s", mcp_url)

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
                            page_cursor = tool_list_page.nextCursor
                            if not page_cursor:
                                break
                            if tool_names_to_find and len(
                                names_of_tools_added
                            ) == len(tool_names_to_find):
                                break
                        tools.extend(fetched_mcp_tools_list)
                        logger.info("[SUB_AGENT] mcp_tools_added count=%s", len(fetched_mcp_tools_list))
            except Exception:
                logger.exception("[SUB_AGENT] error_fetching_mcp_tools")
                pass
    return tools


def _create_combined_hook(trimming_hook: Optional[Callable], img_preprocessor: Optional[Callable]) -> Optional[Callable]:
    """
    Factory function to properly capture hook instances in closure.

    This prevents Python closure bugs where loop variables are captured by reference
    instead of by value, ensuring each agent gets its own independent hook with
    properly captured variables.

    Args:
        trimming_hook: Optional message trimming hook (sync function)
        img_preprocessor: Optional image preprocessing hook (async function)

    Returns:
        Combined async hook function or None if neither hook is provided
    """
    if trimming_hook and img_preprocessor:
        async def combined_hook(state, config):
            # 1. Trim first (when images are just storage paths ~50 tokens each)
            trimming_result = trimming_hook(state)  # Trimming hook is sync, no await
            state = {**state, **trimming_result}
            # 2. Then convert images to signed URLs (or base64 in local dev)
            state = await img_preprocessor(state, config)
            return state
        return combined_hook
    elif img_preprocessor:
        return img_preprocessor
    elif trimming_hook:
        # Wrap trimming_hook to accept (state, config) signature expected by LangGraph
        def wrapped_trimming_hook(state, config):
            return trimming_hook(state)
        return wrapped_trimming_hook
    return None


async def _get_agents(
    tools,
    instructions,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
):
    all_builtin_tools = [write_todos, write_file, read_file, ls, edit_file]
    agents = {}

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
        # Create trimming hook for general-purpose agent
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
            logger.info(
                "[SUB_AGENT] trimming_enabled agent=general-purpose max_tokens=%s",
                gp_model_info.trimming_max_tokens
            )

        # Combine image preprocessor with trimming hook
        # IMPORTANT: Trim FIRST (when images are storage paths), THEN convert images
        gp_combined_hook = _create_combined_hook(gp_trimming_hook, image_preprocessor)

        agents["general-purpose"] = custom_create_react_agent(
            model,
            prompt=append_datetime_to_prompt(GENERAL_PURPOSE_SUBAGENT_PROMPT),
            tools=tools,
            state_schema=state_schema,
            checkpointer=False,
            post_model_hook=post_model_hook,
            pre_model_hook=gp_combined_hook,  # Use combined hook
            enable_image_processing=False,
            name="basic_deepagent",  # For cost tracking graph_name
        )
    # Parent tools (selected for main agent)
    parent_tools_by_name = {
        t.name: t
        for t in ([tool(t) if not isinstance(t, BaseTool) else t for t in tools])
    }
    # Built-in tools that every agent should have
    builtin_tools_by_name = {
        t.name: t
        for t in ([tool(t) if not isinstance(t, BaseTool) else t for t in all_builtin_tools])
    }

    for _agent in subagents:
        # Handle both dictionary (from frontend JSON) and object formats
        if isinstance(_agent, dict):
            agent_name = _agent.get('name', 'unnamed_agent')
            agent_tools = _agent.get('tools', [])
            # Check for model_name field first (new centralized config), then fall back to legacy 'model' field
            agent_model = _agent.get('model_name', None) or _agent.get('model', None)
            agent_prompt = _agent.get('prompt', 'You are a helpful assistant.')
        else:
            # Handle SerializableSubAgent object
            agent_name = getattr(_agent, 'name', 'unnamed_agent')
            agent_tools = getattr(_agent, 'tools', [])
            # Check for model_name field first (new centralized config), then fall back to legacy 'model' field
            agent_model = getattr(_agent, 'model_name', None) or getattr(_agent, 'model', None)
            agent_prompt = getattr(_agent, 'prompt', 'You are a helpful assistant.')

        if config:
            # Fetch sub-agent specific tools (RAG/MCP)
            sub_specific_tools = await _get_tools_for_sub_agent(
                _agent, list(builtin_tools_by_name.values()), config
            )
            # Combine ONLY sub-agent specific tools with built-in tools (do NOT inherit parent's selected MCP tools)
            combined_tools_by_name = {}
            for tool_obj in sub_specific_tools + list(builtin_tools_by_name.values()):
                combined_tools_by_name[getattr(tool_obj, "name", str(tool_obj))] = tool_obj
            _tools = list(combined_tools_by_name.values())
            logger.info("[SUB_AGENT] tools_composition agent=%s sub_specific=%s builtin=%s final=%s",
                        agent_name, len(sub_specific_tools), len(builtin_tools_by_name), len(_tools))
        else:
            if agent_tools:
                _tools = [
                    builtin_tools_by_name[t] for t in agent_tools if t in builtin_tools_by_name
                ]
            else:
                _tools = list(builtin_tools_by_name.values())

        if agent_model:
            if isinstance(agent_model, str):
                # Direct model name string (new centralized config format)
                # Use init_model_simple to get correct max_tokens from registry
                from agent_platform.utils.model_utils import init_model_simple
                sub_model = init_model_simple(model_name=agent_model)
                logger.info("[SUB_AGENT] model_initialized agent=%s model=%s source=string", agent_name, agent_model)
            elif isinstance(agent_model, dict):
                # Legacy dict format with 'model_name' or 'model' key
                if 'model_name' in agent_model or 'model' in agent_model:
                    model_name = agent_model.get('model_name') or agent_model.get('model')
                    # Use init_model_simple to get correct max_tokens from registry
                    from agent_platform.utils.model_utils import init_model_simple
                    sub_model = init_model_simple(model_name=model_name)
                    logger.info("[SUB_AGENT] model_initialized agent=%s model=%s source=dict", agent_name, model_name)
                else:
                    # Fallback for legacy format
                    sub_model = agent_model
                    logger.info("[SUB_AGENT] model_initialized agent=%s source=legacy_dict", agent_name)
            else:
                # Already a model instance
                sub_model = agent_model
                logger.info("[SUB_AGENT] model_initialized agent=%s source=instance", agent_name)
        else:
            # Use parent model
            sub_model = model
            logger.info("[SUB_AGENT] model_initialized agent=%s source=parent", agent_name)

        # Create trimming hook for this sub-agent based on its model
        sub_model_name = None
        if isinstance(agent_model, str):
            sub_model_name = agent_model
        elif isinstance(agent_model, dict):
            sub_model_name = agent_model.get('model_name') or agent_model.get('model')

        # Fallback to parent model name or default
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
            logger.info(
                "[SUB_AGENT] trimming_enabled agent=%s max_tokens=%s",
                agent_name,
                sub_model_info.trimming_max_tokens
            )

        # Combine image preprocessor with trimming hook
        # IMPORTANT: Trim FIRST (when images are storage paths), THEN convert images
        sub_combined_hook = _create_combined_hook(sub_trimming_hook, image_preprocessor)

        logger.info("[SUB_AGENT] tools_assigned agent=%s total=%s", agent_name, len(_tools))
        agents[agent_name] = custom_create_react_agent(
            sub_model,
            prompt=append_datetime_to_prompt(agent_prompt),
            tools=_tools,
            state_schema=state_schema,
            checkpointer=False,
            post_model_hook=post_model_hook,
            pre_model_hook=sub_combined_hook,  # Use combined hook
            enable_image_processing=False,
            name="basic_deepagent",  # For cost tracking graph_name
        )

    return agents


def _get_subagent_description(subagents):
    descriptions = []
    for _agent in subagents:
        # Handle both dictionary (from frontend JSON) and object formats
        if isinstance(_agent, dict):
            name = _agent.get('name', 'Unnamed Agent')
            description = _agent.get('description', 'No description')
        else:
            # Handle SerializableSubAgent object
            name = getattr(_agent, 'name', 'Unnamed Agent')
            description = getattr(_agent, 'description', 'No description')
        descriptions.append(f"- {name}: {description}")
    return descriptions


def _create_task_tool(
    tools,
    instructions,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
):
    other_agents_string = _get_subagent_description(subagents)

    # Build description conditionally
    if not include_general_purpose and not other_agents_string:
        # No agents available - update description accordingly
        task_description = """Launch a new agent to handle complex, multi-step tasks autonomously.

Note: No sub-agents are currently configured. Please add custom sub-agents in the agent configuration to enable task delegation.
""" + TASK_DESCRIPTION_SUFFIX
    elif include_general_purpose:
        task_description = TASK_DESCRIPTION_PREFIX.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX
    else:
        # Has custom subagents but no general-purpose
        task_description_no_gp = """Launch a new agent to handle complex, multi-step tasks autonomously.

Available agent types and the tools they have access to:
{other_agents}
"""
        task_description = task_description_no_gp.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX

    @tool(description=task_description)
    async def task(
        description: str,
        subagent_type: str,
        state: Annotated[DeepAgentState, InjectedState],
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
                "files": result.get("files", {}),
                "messages": [
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task


def _create_sync_task_tool(
    tools,
    instructions,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
    include_general_purpose: bool = True,
):
    # This is a sync function, so we need to run the async _get_agents in an event loop.
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # This is for cases like Jupyter notebooks where an event loop is already running
        import nest_asyncio

        nest_asyncio.apply()
        agents = asyncio.run(
            _get_agents(
                tools,
                instructions,
                subagents,
                model,
                state_schema,
                post_model_hook,
                config,
                include_general_purpose,
            )
        )
    else:
        agents = asyncio.run(
            _get_agents(
                tools,
                instructions,
                subagents,
                model,
                state_schema,
                post_model_hook,
                config,
                include_general_purpose,
            )
        )

    other_agents_string = _get_subagent_description(subagents)

    # Build description conditionally
    if not include_general_purpose and not other_agents_string:
        # No agents available - update description accordingly
        task_description = """Launch a new agent to handle complex, multi-step tasks autonomously.

Note: No sub-agents are currently configured. Please add custom sub-agents in the agent configuration to enable task delegation.
""" + TASK_DESCRIPTION_SUFFIX
    elif include_general_purpose:
        task_description = TASK_DESCRIPTION_PREFIX.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX
    else:
        # Has custom subagents but no general-purpose
        task_description_no_gp = """Launch a new agent to handle complex, multi-step tasks autonomously.

Available agent types and the tools they have access to:
{other_agents}
"""
        task_description = task_description_no_gp.format(other_agents="\n".join(other_agents_string)) + TASK_DESCRIPTION_SUFFIX

    @tool(description=task_description)
    def task(
        description: str,
        subagent_type: str,
        state: Annotated[DeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        if subagent_type not in agents:
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
        sub_agent = agents[subagent_type]
        # Create a new state dict for the sub-agent invocation
        sub_agent_state = state.copy()
        sub_agent_state["messages"] = [HumanMessage(content=description)]
        # Pass config so sub-agent can access run_id for cost tracking
        result = sub_agent.invoke(sub_agent_state, config)
        return Command(
            update={
                "files": result.get("files", {}),
                "messages": [
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task