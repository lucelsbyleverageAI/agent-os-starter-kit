try:
    from .sub_agent import _create_task_tool, _create_sync_task_tool
    from .model import get_default_model
    from .deep_agent_toolkit import write_todos, write_file, read_file, ls, edit_file
    from .state import DeepAgentState
    from .interrupt import create_interrupt_hook, ToolInterruptConfig
    from .image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing
except ImportError:
    from agent_platform.agents.deepagents.sub_agent import _create_task_tool, _create_sync_task_tool
    from agent_platform.agents.deepagents.model import get_default_model
    from agent_platform.agents.deepagents.deep_agent_toolkit import write_todos, write_file, read_file, ls, edit_file
    from agent_platform.agents.deepagents.state import DeepAgentState
    from agent_platform.agents.deepagents.interrupt import create_interrupt_hook, ToolInterruptConfig
    from agent_platform.agents.deepagents.image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing
from typing import Sequence, Union, Callable, Any, TypeVar, Type, Optional
from langchain_core.tools import BaseTool, tool
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langgraph.types import Checkpointer
from .custom_react_agent import custom_create_react_agent
from langchain_core.runnables import RunnableConfig
from .builder import SerializableSubAgent


StateSchema = TypeVar("StateSchema", bound=DeepAgentState)
StateSchemaType = Type[StateSchema]


base_prompt_with_task = """You have access to a number of standard tools

## `write_todos`

You have access to the `write_todos` tools to help you manage and plan tasks. Use these tools VERY frequently to ensure that you are tracking your tasks and giving the user visibility into your progress.
These tools are also EXTREMELY helpful for planning tasks, and for breaking down larger complex tasks into smaller steps. If you do not use this tool when planning, you may forget to do important tasks - and that is unacceptable.

It is critical that you mark todos as completed as soon as you are done with a task. Do not batch up multiple tasks before marking them as completed.

## `task`

- When doing web search, prefer to use the `task` tool in order to reduce context usage.

## Tool Authentication Errors

If a tool throws an error requiring authentication, provide the user with a Markdown link to the authentication page and prompt them to authenticate (but never make up an authentication URL, only use the one provided by the tool).
"""

base_prompt_without_task = """You have access to a number of standard tools

## `write_todos`

You have access to the `write_todos` tools to help you manage and plan tasks. Use these tools VERY frequently to ensure that you are tracking your tasks and giving the user visibility into your progress.
These tools are also EXTREMELY helpful for planning tasks, and for breaking down larger complex tasks into smaller steps. If you do not use this tool when planning, you may forget to do important tasks - and that is unacceptable.

It is critical that you mark todos as completed as soon as you are done with a task. Do not batch up multiple tasks before marking them as completed.

## Tool Authentication Errors

If a tool throws an error requiring authentication, provide the user with a Markdown link to the authentication page and prompt them to authenticate (but never make up an authentication URL, only use the one provided by the tool).
"""


def _agent_builder(
    tools: Sequence[Union[BaseTool, Callable, dict[str, Any]]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: list[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    builtin_tools: Optional[list[str]] = None,
    interrupt_config: Optional[ToolInterruptConfig] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    is_async: bool = False,
    enable_image_processing: bool = False,
    runnable_config: Optional[RunnableConfig] = None,
    include_general_purpose_agent: bool = True,
):
    # Determine if any sub-agents are available
    has_subagents = (subagents and len(subagents) > 0) or include_general_purpose_agent

    # Use appropriate base prompt depending on whether task tool will be available
    base_prompt = base_prompt_with_task if has_subagents else base_prompt_without_task
    prompt = instructions + "\n\n" + base_prompt

    all_builtin_tools = [write_todos, write_file, read_file, ls, edit_file]

    if builtin_tools is not None:
        tools_by_name = {}
        for tool_ in all_builtin_tools:
            if not isinstance(tool_, BaseTool):
                tool_ = tool(tool_)
            tools_by_name[tool_.name] = tool_
        # Only include built-in tools whose names are in the specified list
        built_in_tools = [tools_by_name[_tool] for _tool in builtin_tools]
    else:
        built_in_tools = all_builtin_tools

    if model is None:
        model = get_default_model()


    state_schema = state_schema or DeepAgentState

    # Should never be the case that both are specified
    if post_model_hook and interrupt_config:
        raise ValueError(
            "Cannot specify both post_model_hook and interrupt_config together. "
            "Use either interrupt_config for tool interrupts or post_model_hook for custom post-processing."
        )
    elif post_model_hook is not None:
        selected_post_model_hook = post_model_hook
    elif interrupt_config is not None:
        selected_post_model_hook = create_interrupt_hook(interrupt_config)
    else:
        selected_post_model_hook = None

    # Only create task tool if there are sub-agents available
    if has_subagents:
        if not is_async:
            task_tool = _create_sync_task_tool(
                list(tools) + built_in_tools,
                instructions,
                subagents or [],
                model,
                state_schema,
                selected_post_model_hook,
                runnable_config,
                include_general_purpose_agent,
            )
        else:
            task_tool = _create_task_tool(
                list(tools) + built_in_tools,
                instructions,
                subagents or [],
                model,
                state_schema,
                selected_post_model_hook,
                runnable_config,
                include_general_purpose_agent,
            )

        all_tools = built_in_tools + list(tools) + [task_tool]
    else:
        # No sub-agents available, don't include task tool
        all_tools = built_in_tools + list(tools)

    return custom_create_react_agent(
        model,
        prompt=prompt,
        tools=all_tools,
        state_schema=state_schema,
        post_model_hook=selected_post_model_hook,
        pre_model_hook=pre_model_hook,
        config_schema=config_schema,
        checkpointer=checkpointer,
        enable_image_processing=enable_image_processing,
    )


def create_deep_agent(
    tools: Sequence[Union[BaseTool, Callable, dict[str, Any]]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: list[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    builtin_tools: Optional[list[str]] = None,
    interrupt_config: Optional[ToolInterruptConfig] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    enable_image_processing: bool = False,
    include_general_purpose_agent: bool = True,
    **kwargs,
):
    """Create a deep agent.

    This agent will by default have access to a tool to write todos (write_todos),
    and then four file editing tools: write_file, ls, read_file, edit_file.

    Args:
        tools: The additional tools the agent should have access to.
        instructions: The additional instructions the agent should have. Will go in
            the system prompt.
        model: The model to use.
        subagents: The subagents to use. Each subagent should be a dictionary with the
            following keys:
                - `name`
                - `description` (used by the main agent to decide whether to call the sub agent)
                - `prompt` (used as the system prompt in the subagent)
                - (optional) `tools`
                - (optional) `model` (either a LanguageModelLike instance or dict settings)
        state_schema: The schema of the deep agent. Should subclass from DeepAgentState
        builtin_tools: If not provided, all built-in tools are included. If provided,
            only the specified built-in tools are included.
        interrupt_config: Optional Dict[str, HumanInterruptConfig] mapping tool names to interrupt configs.
        config_schema: The schema of the deep agent.
        post_model_hook: Custom post model hook
        checkpointer: Optional checkpointer for persisting agent state between runs.
        enable_image_processing: Whether to enable the image processing node.
    """
    return _agent_builder(
        tools=tools,
        instructions=instructions,
        model=model,
        subagents=subagents,
        state_schema=state_schema,
        builtin_tools=builtin_tools,
        interrupt_config=interrupt_config,
        config_schema=config_schema,
        checkpointer=checkpointer,
        post_model_hook=post_model_hook,
        pre_model_hook=pre_model_hook,
        is_async=False,
        enable_image_processing=enable_image_processing,
        runnable_config=kwargs.get("runnable_config"),
        include_general_purpose_agent=include_general_purpose_agent,
    )


def async_create_deep_agent(
    tools: Sequence[Union[BaseTool, Callable, dict[str, Any]]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: list[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    builtin_tools: Optional[list[str]] = None,
    interrupt_config: Optional[ToolInterruptConfig] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    enable_image_processing: bool = False,
    include_general_purpose_agent: bool = True,
    **kwargs,
):
    """Create a deep agent.

    This agent will by default have access to a tool to write todos (write_todos),
    and then four file editing tools: write_file, ls, read_file, edit_file.

    Args:
        tools: The additional tools the agent should have access to.
        instructions: The additional instructions the agent should have. Will go in
            the system prompt.
        model: The model to use.
        subagents: The subagents to use. Each subagent should be a dictionary with the
            following keys:
                - `name`
                - `description` (used by the main agent to decide whether to call the sub agent)
                - `prompt` (used as the system prompt in the subagent)
                - (optional) `tools`
                - (optional) `model` (either a LanguageModelLike instance or dict settings)
        state_schema: The schema of the deep agent. Should subclass from DeepAgentState
        builtin_tools: If not provided, all built-in tools are included. If provided,
            only the specified built-in tools are included.
        interrupt_config: Optional Dict[str, HumanInterruptConfig] mapping tool names to interrupt configs.
        config_schema: The schema of the deep agent.
        post_model_hook: Custom post model hook
        checkpointer: Optional checkpointer for persisting agent state between runs.
        enable_image_processing: Whether to enable the image processing node.
    """
    return _agent_builder(
        tools=tools,
        instructions=instructions,
        model=model,
        subagents=subagents,
        state_schema=state_schema,
        builtin_tools=builtin_tools,
        interrupt_config=interrupt_config,
        config_schema=config_schema,
        checkpointer=checkpointer,
        post_model_hook=post_model_hook,
        pre_model_hook=pre_model_hook,
        is_async=True,
        enable_image_processing=enable_image_processing,
        runnable_config=kwargs.get("runnable_config"),
        include_general_purpose_agent=include_general_purpose_agent,
    )