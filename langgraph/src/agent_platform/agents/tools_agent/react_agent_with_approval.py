"""
Custom ReAct Agent with Approval Support

This module provides a custom ReAct agent implementation that supports
human-in-the-loop tool approval at the graph level. Unlike the ToolNode
override approach, this implementation uses explicit routing to handle
approval workflows.

The implementation follows the standard ReAct pattern with approval routing:
1. Agent node: Calls the model to get next action
2. Route node: Checks if tool calls require approval
3. Approval node: Handles human approval workflow (if needed)
4. Tools node: Executes approved tool calls
5. Router: Decides whether to continue or end

Key difference: Approval is handled via graph-level routing, not ToolNode overrides.
This ensures compatibility with both v1 and v2 LangGraph execution modes.
"""

from typing import Literal, Sequence, Union, Callable, Any, Optional, cast
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.types import interrupt
from typing_extensions import TypedDict, Annotated

from agent_platform.utils.tool_approval_utils import (
    should_require_approval,
    create_tool_approval_interrupt,
    process_tool_approval_response,
)
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
    for specific tool calls. Approval is handled via explicit graph routing.

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

    # Create standard tool node for execution
    tool_node = ToolNode(tools=tools, handle_tool_errors=True)

    # Bind tools to model
    if tools:
        model = model.bind_tools(tools)

    # Define the agent node
    async def call_model(state: AgentState, config: RunnableConfig) -> dict:
        """Call the model to get the next action."""
        logger.info("[call_model] === AGENT NODE STARTED ===")
        messages = state["messages"]
        logger.info("[call_model] Input: %d message(s) in state", len(messages))

        # Apply pre_model_hook if provided
        if pre_model_hook:
            logger.info("[call_model] Applying pre_model_hook...")
            try:
                if callable(pre_model_hook):
                    # Hook might be sync or async
                    import inspect
                    if inspect.iscoroutinefunction(pre_model_hook):
                        hook_result = await pre_model_hook(state, config)
                    else:
                        # Handle both 1-arg and 2-arg callables
                        if pre_model_hook.__code__.co_argcount > 1:
                            hook_result = pre_model_hook(state, config)
                        else:
                            hook_result = pre_model_hook(state)

                    # If hook returns a state dict, use it
                    if isinstance(hook_result, dict):
                        state = hook_result
                        messages = state.get("messages", messages)
                        logger.info("[call_model] Hook modified state, now %d message(s)", len(messages))
                    else:
                        logger.info("[call_model] Hook completed (no state modification)")
            except Exception:
                logger.exception("[call_model] pre_model_hook failed")

        # Add prompt as system message if provided
        if prompt:
            messages = [SystemMessage(content=prompt)] + list(messages)
            logger.debug("[call_model] Added system prompt to messages")

        # Call the model
        logger.info("[call_model] Invoking model with %d message(s)...", len(messages))
        response = await model.ainvoke(messages, config)
        logger.info("[call_model] Model responded")

        num_tool_calls = len(response.tool_calls) if hasattr(response, "tool_calls") else 0
        logger.info(
            "[call_model] Response has %d tool call(s): %s",
            num_tool_calls,
            [tc["name"] for tc in response.tool_calls] if num_tool_calls > 0 else "[]"
        )

        logger.info("[call_model] === AGENT NODE COMPLETED ===")
        return {"messages": [response]}

    # Define the approval node
    async def approval_node(state: AgentState, config: RunnableConfig) -> dict:
        """
        Handle approval workflow for tools requiring human approval.

        This node:
        1. Extracts tool calls from the last AI message
        2. For each tool requiring approval, creates an interrupt
        3. Waits for human response
        4. Processes the response (accept/edit/respond/reject)
        5. Returns appropriate messages to continue execution
        """
        logger.info("[approval_node] === APPROVAL NODE STARTED ===")
        messages = state["messages"]
        last_message = messages[-1]

        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            logger.warning("[approval_node] Called with no tool calls in last message")
            return {"messages": []}

        logger.info(
            "[approval_node] Found %d tool call(s) in last message",
            len(last_message.tool_calls)
        )

        tool_messages = []

        # Process each tool call
        for idx, tool_call in enumerate(last_message.tool_calls, 1):
            tool_name = tool_call.get("name")
            tool_call_id = tool_call.get("id", "unknown")

            logger.info(
                "[approval_node] [%d/%d] Processing tool call: %s (id=%s, requires_approval=%s)",
                idx,
                len(last_message.tool_calls),
                tool_name,
                tool_call_id,
                should_require_approval(tool_name, tool_approvals)
            )

            # Check if this specific tool requires approval
            if not should_require_approval(tool_name, tool_approvals):
                # This shouldn't happen due to routing, but handle gracefully
                logger.warning(
                    "[approval_node] Tool %s routed to approval but doesn't require it - skipping",
                    tool_name
                )
                continue

            # Create interrupt for approval
            logger.info(
                "[approval_node] Creating interrupt data for tool: %s with args: %s",
                tool_name,
                tool_call.get("args")
            )
            interrupt_data = create_tool_approval_interrupt(
                tool_call,
                description=f"**Tool Approval Required**\n\nThe agent wants to call `{tool_name}`.\n\nReview the arguments and choose an action."
            )

            # This will pause execution until human responds
            logger.info("[approval_node] ⏸️  PAUSING execution - waiting for human response for tool: %s", tool_name)
            human_response_raw = interrupt(interrupt_data)
            logger.info("[approval_node] ▶️  RESUMED execution - received response for tool: %s", tool_name)

            # interrupt() returns a list when resuming - extract the actual response
            # The response format from frontend is: Command (dict with type, args, etc.)
            logger.debug("[approval_node] Raw response type: %s, value: %s", type(human_response_raw), human_response_raw)

            if isinstance(human_response_raw, list) and len(human_response_raw) > 0:
                human_response = human_response_raw[0]
                logger.info("[approval_node] Extracted response from list (length=%d)", len(human_response_raw))
            else:
                human_response = human_response_raw
                logger.info("[approval_node] Using response as-is (not a list)")

            response_type = human_response.get("type") if isinstance(human_response, dict) else "unknown"
            logger.info(
                "[approval_node] Received human response type=%s for tool=%s",
                response_type,
                tool_name
            )

            # Process the human response
            logger.info("[approval_node] Processing human response...")
            result = process_tool_approval_response(human_response, tool_call)
            logger.info("[approval_node] Response processed, result type: %s", type(result).__name__)

            if isinstance(result, ToolMessage):
                # Human provided feedback or rejected - add message for agent
                logger.info(
                    "[approval_node] ❌ Tool rejected or feedback provided - adding ToolMessage to state"
                )
                logger.debug("[approval_node] ToolMessage content: %s", result.content[:200] if result.content else "empty")
                tool_messages.append(result)
            elif result is not None:
                # Tool was approved (possibly with edited args) - execute it
                logger.info(
                    "[approval_node] ✅ Tool approved - executing: %s (args: %s)",
                    tool_name,
                    result.get("args") if isinstance(result, dict) else "N/A"
                )

                # Execute the tool using the tool node
                # We need to create a temporary state with just this tool call
                temp_message = AIMessage(
                    content="",
                    tool_calls=[result],
                    id=last_message.id
                )
                temp_state = {"messages": [temp_message]}

                logger.info("[approval_node] Invoking tool node for execution...")
                # Execute the tool
                tool_result = await tool_node.ainvoke(temp_state, config)
                logger.info(
                    "[approval_node] Tool execution completed, result keys: %s",
                    list(tool_result.keys()) if tool_result else "None"
                )

                # Add the tool message to our results
                if tool_result and "messages" in tool_result:
                    num_messages = len(tool_result["messages"])
                    logger.info("[approval_node] Adding %d tool result message(s) to state", num_messages)
                    tool_messages.extend(tool_result["messages"])
                else:
                    logger.warning("[approval_node] Tool execution returned no messages")
            else:
                # Null result - should not happen
                logger.error("[approval_node] ⚠️  Null result from approval response - this should not happen!")
                tool_messages.append(
                    ToolMessage(
                        content="Tool approval response was invalid",
                        tool_call_id=tool_call_id,
                        name=tool_name or "unknown"
                    )
                )

        logger.info(
            "[approval_node] === APPROVAL NODE COMPLETED === Returning %d message(s)",
            len(tool_messages)
        )
        return {"messages": tool_messages}

    # Define the router after agent
    def route_after_agent(state: AgentState) -> Literal["approval", "tools", "__end__"]:
        """
        Route based on whether tool calls require approval.

        Returns:
            - "approval": If any tool call requires human approval
            - "tools": If there are tool calls but none require approval
            - END: If no tool calls (agent finished)
        """
        logger.info("[route_after_agent] === ROUTING AFTER AGENT ===")
        messages = state["messages"]
        last_message = messages[-1]

        logger.info(
            "[route_after_agent] Last message type: %s, is_AIMessage: %s",
            type(last_message).__name__,
            isinstance(last_message, AIMessage)
        )

        # Check if we have tool calls
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            logger.info("[route_after_agent] ➡️  No tool calls found → Routing to END")
            return END

        logger.info(
            "[route_after_agent] Found %d tool call(s): %s",
            len(last_message.tool_calls),
            [call["name"] for call in last_message.tool_calls]
        )

        # Check if any tool requires approval
        tools_requiring_approval = [
            call["name"]
            for call in last_message.tool_calls
            if should_require_approval(call["name"], tool_approvals)
        ]

        tools_not_requiring_approval = [
            call["name"]
            for call in last_message.tool_calls
            if not should_require_approval(call["name"], tool_approvals)
        ]

        logger.info(
            "[route_after_agent] Tool approval check: %d require approval, %d do not",
            len(tools_requiring_approval),
            len(tools_not_requiring_approval)
        )

        if tools_requiring_approval:
            logger.info(
                "[route_after_agent] ⏸️  Tools requiring approval: %s → Routing to APPROVAL node",
                tools_requiring_approval
            )
            return "approval"
        else:
            logger.info(
                "[route_after_agent] ▶️  No tools require approval (all tools: %s) → Routing to TOOLS node",
                tools_not_requiring_approval
            )
            return "tools"

    # Define router after approval node
    def route_after_approval(state: AgentState) -> Literal["agent", "tools", "__end__"]:
        """
        Route after approval node.

        If approval node added ToolMessages (feedback/rejection), route back to agent.
        Otherwise, we shouldn't reach here (approval node handles execution).
        """
        messages = state["messages"]

        # Check if last message is a ToolMessage (feedback/rejection)
        if messages and isinstance(messages[-1], ToolMessage):
            logger.debug("[route_after_approval] Tool feedback provided, routing to agent")
            return "agent"

        # If we have tool calls still pending, this shouldn't happen
        # but route back to agent to be safe
        logger.debug("[route_after_approval] Routing back to agent")
        return "agent"

    # Build the graph
    workflow = StateGraph(AgentState, config_schema=config_schema)

    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("approval", approval_node)
    workflow.add_node("tools", tool_node)

    # Add edges
    workflow.set_entry_point("agent")

    # Conditional routing after agent
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "approval": "approval",
            "tools": "tools",
            END: END
        }
    )

    # After approval, route back to agent (tool results are already in state)
    workflow.add_edge("approval", "agent")

    # After tools (no approval needed), route back to agent
    workflow.add_edge("tools", "agent")

    # Compile and return
    compiled = workflow.compile()

    logger.info("[create_react_agent_with_approval] Agent graph compiled successfully")

    return compiled
