"""
Custom ReAct Agent with Approval Support

This module provides a minimal custom ReAct agent implementation that supports
human-in-the-loop tool approval. It's designed to be a drop-in replacement for
LangGraph's create_react_agent but with approval capabilities.

The implementation follows the standard ReAct pattern:
1. Agent node: Calls the model to get next action
2. Tools node: Executes tool calls (with approval if configured)
3. Router: Decides whether to continue or end

Key difference: Uses ApprovalToolNode instead of ToolNode for tool execution.
"""

from typing import Literal, Sequence, Union, Callable, Any, Optional
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from typing_extensions import TypedDict, Annotated

from agent_platform.utils.approval_tool_node import ApprovalToolNode
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


class AgentState(TypedDict):
    """The state of the agent."""
    messages: Annotated[list[BaseMessage], add_messages]


def create_react_agent_with_approval(
    model: BaseChatModel,
    tools: Sequence[Union[BaseTool, Callable]],
    *,
    tool_approvals: Optional[dict[str, bool]] = None,
    prompt: Optional[str] = None,
    pre_model_hook: Optional[Callable] = None,
    config_schema: Optional[type] = None,
    **kwargs
) -> Runnable:
    """
    Create a ReAct agent with human-in-the-loop tool approval support.

    This function creates a graph-based agent that follows the ReAct pattern
    (Reasoning and Acting) with the added capability of requiring human approval
    for specific tool calls.

    Args:
        model: The language model to use for the agent
        tools: List of tools the agent can use
        tool_approvals: Dict mapping tool names to approval requirements
        prompt: System prompt for the agent (prepended to messages)
        pre_model_hook: Optional hook to run before calling the model
        config_schema: Optional Pydantic schema for configuration
        **kwargs: Additional arguments

    Returns:
        Compiled StateGraph ready for execution

    Example:
        ```python
        from langchain_anthropic import ChatAnthropic
        from langchain_core.tools import tool

        @tool
        def dangerous_operation(x: str) -> str:
            \"\"\"Perform a dangerous operation.\"\"\"
            return f"Executed: {x}"

        model = ChatAnthropic(model="claude-3-5-sonnet-20241022")
        agent = create_react_agent_with_approval(
            model=model,
            tools=[dangerous_operation],
            tool_approvals={"dangerous_operation": True},
            prompt="You are a helpful assistant."
        )

        result = agent.invoke({"messages": [("user", "Do something")]})
        ```
    """
    tool_approvals = tool_approvals or {}

    logger.info(
        "[create_react_agent_with_approval] Creating agent with %d tools, %d require approval",
        len(tools),
        sum(1 for v in tool_approvals.values() if v)
    )

    # Bind tools to model
    if tools:
        model = model.bind_tools(tools)

    # Create the approval-aware tool node
    tool_node = ApprovalToolNode(
        tools=tools,
        tool_approvals=tool_approvals,
        handle_tool_errors=True
    )

    # Define the agent node
    async def call_model(state: AgentState, config: RunnableConfig) -> dict:
        """Call the model to get the next action."""
        messages = state["messages"]

        # Apply pre_model_hook if provided
        if pre_model_hook:
            try:
                if callable(pre_model_hook):
                    # Hook might modify state or return modified state
                    hook_result = pre_model_hook(state, config) if pre_model_hook.__code__.co_argcount > 1 else pre_model_hook(state)

                    # If hook returns a state dict, use it
                    if isinstance(hook_result, dict):
                        state = hook_result
                        messages = state.get("messages", messages)
            except Exception:
                logger.exception("[call_model] pre_model_hook failed")

        # Add prompt as system message if provided
        if prompt:
            from langchain_core.messages import SystemMessage
            messages = [SystemMessage(content=prompt)] + list(messages)

        # Call the model
        response = await model.ainvoke(messages, config)

        logger.debug(
            "[call_model] Model response has %d tool calls",
            len(response.tool_calls) if hasattr(response, "tool_calls") else 0
        )

        return {"messages": [response]}

    # Define the router
    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        """Determine if we should continue to tools or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # If there are tool calls, continue to tools
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            logger.debug("[should_continue] Routing to tools")
            return "tools"

        # Otherwise end
        logger.debug("[should_continue] Routing to end")
        return END

    # Build the graph
    workflow = StateGraph(AgentState, config_schema=config_schema)

    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    # Add edges
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    workflow.add_edge("tools", "agent")

    # Compile and return
    compiled = workflow.compile()

    logger.info("[create_react_agent_with_approval] Agent graph compiled successfully")

    return compiled
