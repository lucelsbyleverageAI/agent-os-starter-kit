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
)
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
            enabled_tools = rag_config.get('enabled_tools', ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"])
        else:
            langconnect_api_url = getattr(rag_config, 'langconnect_api_url', None)
            collections = getattr(rag_config, 'collections', [])
            enabled_tools = getattr(rag_config, 'enabled_tools', ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"])
        
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


async def _get_agents(
    tools,
    instructions,
    subagents: list[SerializableSubAgent],
    model,
    state_schema,
    post_model_hook: Optional[Callable] = None,
    config: Optional[RunnableConfig] = None,
):
    all_builtin_tools = [write_todos, write_file, read_file, ls, edit_file]
    agents = {
        "general-purpose": custom_create_react_agent(
            model, prompt=GENERAL_PURPOSE_SUBAGENT_PROMPT, tools=tools, state_schema=state_schema, checkpointer=False, post_model_hook=post_model_hook, enable_image_processing=False
        )
    }
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
                sub_model = init_model(
                    ModelConfig(
                        model_name=agent_model,
                        retry=RetryConfig(max_retries=0),  # Disable retry wrapper for .bind_tools()
                    )
                )
                logger.info("[SUB_AGENT] model_initialized agent=%s model=%s source=string", agent_name, agent_model)
            elif isinstance(agent_model, dict):
                # Legacy dict format with 'model_name' or 'model' key
                if 'model_name' in agent_model or 'model' in agent_model:
                    model_name = agent_model.get('model_name') or agent_model.get('model')
                    sub_model = init_model(
                        ModelConfig(
                            model_name=model_name,
                            retry=RetryConfig(max_retries=0),  # Disable retry wrapper for .bind_tools()
                        )
                    )
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

        logger.info("[SUB_AGENT] tools_assigned agent=%s total=%s", agent_name, len(_tools))
        agents[agent_name] = custom_create_react_agent(
            sub_model,
            prompt=agent_prompt,
            tools=_tools,
            state_schema=state_schema,
            checkpointer=False,
            post_model_hook=post_model_hook,
            enable_image_processing=False,
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
):
    other_agents_string = _get_subagent_description(subagents)

    @tool(
        description=TASK_DESCRIPTION_PREFIX.format(other_agents=other_agents_string)
        + TASK_DESCRIPTION_SUFFIX
    )
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
        )
        if subagent_type not in agents:
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
        sub_agent = agents[subagent_type]
        # Create a new state dict for the sub-agent invocation
        sub_agent_state = state.copy()
        sub_agent_state["messages"] = [HumanMessage(content=description)]
        result = await sub_agent.ainvoke(sub_agent_state)
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
            )
        )

    other_agents_string = _get_subagent_description(subagents)

    @tool(
        description=TASK_DESCRIPTION_PREFIX.format(other_agents=other_agents_string)
        + TASK_DESCRIPTION_SUFFIX
    )
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
        result = sub_agent.invoke(sub_agent_state)
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