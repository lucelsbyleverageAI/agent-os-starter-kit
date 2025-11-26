"""Agent builder for Skills DeepAgent.

This is a local version of the agent builder that:
1. Uses SkillsDeepAgentState
2. Includes write_todos as built-in, plus run_code and run_command from tools param
3. Uses prompts from prompts.py (which includes tools, skills, sandbox, and date)
4. Does NOT append any additional prompt content (prompts.py handles everything)
"""

from typing import Sequence, Union, Callable, Any, Optional, Type, TypeVar, List
from langchain_core.tools import BaseTool, tool
from langchain_core.language_models import LanguageModelLike
from langgraph.types import Checkpointer
from langchain_core.runnables import RunnableConfig

try:
    from .state import SkillsDeepAgentState
    from .toolkit import write_todos
    from .sub_agent import _create_task_tool, _create_sync_task_tool
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import SkillsDeepAgentState
    from agent_platform.agents.deepagents.skills_deepagent.toolkit import write_todos
    from agent_platform.agents.deepagents.skills_deepagent.sub_agent import _create_task_tool, _create_sync_task_tool

from agent_platform.agents.deepagents.custom_react_agent import custom_create_react_agent
from agent_platform.agents.deepagents.model import get_default_model
from agent_platform.agents.deepagents.builder import SerializableSubAgent
from agent_platform.utils.message_utils import create_image_preprocessor


StateSchema = TypeVar("StateSchema", bound=SkillsDeepAgentState)
StateSchemaType = Type[StateSchema]


def skills_agent_builder(
    tools: Sequence[Union[BaseTool, Callable]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: List[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    is_async: bool = False,
    runnable_config: Optional[RunnableConfig] = None,
    include_general_purpose_agent: bool = True,
):
    """Build a Skills DeepAgent with sandbox-only filesystem.

    Args:
        tools: Additional tools (should include execute_in_sandbox)
        instructions: Complete system prompt from prompts.py (includes tools, skills, sandbox, date)
        model: Language model to use
        subagents: List of sub-agent configurations
        state_schema: State schema (defaults to SkillsDeepAgentState)
        config_schema: Configuration schema
        checkpointer: Optional checkpointer
        post_model_hook: Post-model processing hook
        pre_model_hook: Pre-model processing hook (typically trimming)
        is_async: Whether to use async task tool
        runnable_config: LangGraph runtime configuration
        include_general_purpose_agent: Whether to include general-purpose sub-agent
    """
    has_subagents = (subagents and len(subagents) > 0) or include_general_purpose_agent

    # Use instructions directly - prompts.py already includes everything:
    # user prompt, built-in tools, sandbox environment, skills, guidelines, and date
    prompt = instructions

    # Only write_todos as built-in - execute_in_sandbox comes from `tools`
    built_in_tools = [write_todos]

    if model is None:
        model = get_default_model()

    state_schema = state_schema or SkillsDeepAgentState

    # Get LangConnect URL for image preprocessing
    langconnect_api_url = "http://langconnect:8080"
    if runnable_config:
        rag_config = runnable_config.get("configurable", {}).get("rag", {})
        if isinstance(rag_config, dict):
            langconnect_api_url = rag_config.get("langconnect_api_url", langconnect_api_url)

    image_hook = create_image_preprocessor(langconnect_api_url)

    # Combine hooks: trim first, then process images
    combined_pre_hook = None
    if pre_model_hook and image_hook:
        async def combined_hook(state, config):
            # 1. Trim first (when images are just storage paths ~50 tokens each)
            trimming_result = pre_model_hook(state)
            state = {**state, **trimming_result}
            # 2. Then convert images to signed URLs (or base64 in local dev)
            state = await image_hook(state, config)
            return state
        combined_pre_hook = combined_hook
    elif image_hook:
        combined_pre_hook = image_hook
    elif pre_model_hook:
        combined_pre_hook = pre_model_hook

    # Create task tool if sub-agents available
    if has_subagents:
        # Pass execute_in_sandbox to sub-agents via tools
        if not is_async:
            task_tool = _create_sync_task_tool(
                list(tools) + built_in_tools,  # includes execute_in_sandbox
                instructions,
                subagents or [],
                model,
                state_schema,
                post_model_hook,
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
                post_model_hook,
                runnable_config,
                include_general_purpose_agent,
            )
        all_tools = built_in_tools + list(tools) + [task_tool]
    else:
        all_tools = built_in_tools + list(tools)

    return custom_create_react_agent(
        model,
        prompt=prompt,
        tools=all_tools,
        state_schema=state_schema,
        post_model_hook=post_model_hook,
        pre_model_hook=combined_pre_hook,
        config_schema=config_schema,
        checkpointer=checkpointer,
    )


def async_create_skills_agent(
    tools: Sequence[Union[BaseTool, Callable]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: List[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    runnable_config: Optional[RunnableConfig] = None,
    include_general_purpose_agent: bool = True,
):
    """Create an async Skills DeepAgent."""
    return skills_agent_builder(
        tools=tools,
        instructions=instructions,
        model=model,
        subagents=subagents,
        state_schema=state_schema,
        config_schema=config_schema,
        checkpointer=checkpointer,
        post_model_hook=post_model_hook,
        pre_model_hook=pre_model_hook,
        is_async=True,
        runnable_config=runnable_config,
        include_general_purpose_agent=include_general_purpose_agent,
    )


def create_skills_agent(
    tools: Sequence[Union[BaseTool, Callable]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: List[SerializableSubAgent] = None,
    state_schema: Optional[StateSchemaType] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    runnable_config: Optional[RunnableConfig] = None,
    include_general_purpose_agent: bool = True,
):
    """Create a sync Skills DeepAgent."""
    return skills_agent_builder(
        tools=tools,
        instructions=instructions,
        model=model,
        subagents=subagents,
        state_schema=state_schema,
        config_schema=config_schema,
        checkpointer=checkpointer,
        post_model_hook=post_model_hook,
        pre_model_hook=pre_model_hook,
        is_async=False,
        runnable_config=runnable_config,
        include_general_purpose_agent=include_general_purpose_agent,
    )
