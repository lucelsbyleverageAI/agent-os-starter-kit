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

from typing import Literal, Sequence, Union, Callable, Any, Optional, Type, Tuple, cast
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
from agent_platform.utils.usage_tracking import (
    extract_usage_from_response,
    extract_run_context,
    record_usage,
    UsageAccumulator,
)
from agent_platform.utils.sse_cost_capture import (
    set_current_run_id,
    get_and_clear_captured_cost,
    get_and_clear_captured_model,
    get_and_clear_captured_tokens,
)
from agent_platform.sentry import get_logger

logger = get_logger(__name__)

# Global usage accumulator for tracking across calls
# This is stored per-thread via configurable
_usage_accumulators: dict = {}

# Costs are now captured at the HTTP level via sse_cost_capture module
# which intercepts SSE streams to extract cost from the final chunk


class AgentState(TypedDict):
    """The default state of the agent."""
    messages: Annotated[list[BaseMessage], add_messages]


def create_react_agent_with_approval(
    model: BaseChatModel,
    tools: Sequence[Union[BaseTool, Callable]],
    *,
    tool_approvals: Optional[dict[str, bool]] = None,
    prompt: Optional[str] = None,
    pre_model_hook: Optional[Callable] = None,
    config_schema: Optional[type] = None,
    state_schema: Optional[Type[TypedDict]] = None,
    file_attachment_processor: Optional[Union[Callable, Tuple[Callable, Callable]]] = None,
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
        state_schema: Optional TypedDict schema for state (default: AgentState)
        file_attachment_processor: Optional callable(s) for file attachment processing
            Can be a single function or a tuple of (emit_status_fn, main_fn)
            for progressive UI (loading indicator before slow initialization)
        **kwargs: Additional arguments

    Returns:
        Compiled StateGraph ready for execution

    Example:
        ```python
        from agent_platform.utils.model_utils import init_model_simple
        from langchain_core.tools import tool

        @tool
        def dangerous_operation(x: str) -> str:
            \"\"\"Perform a dangerous operation.\"\"\"
            return f"Executed: {x}"

        model = init_model_simple(model_name="anthropic/claude-sonnet-4")
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

    # Use provided state_schema or default to AgentState
    effective_state_schema = state_schema or AgentState

    logger.info(
        "[create_react_agent_with_approval] Creating agent with %d tools, %d require approval, state_schema=%s",
        len(tools),
        sum(1 for v in tool_approvals.values() if v),
        effective_state_schema.__name__
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
                        # Check for llm_input_messages first (set by trimming hook), fall back to messages
                        messages = state.get("llm_input_messages") or state.get("messages", messages)
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

        # Extract run context before model invocation
        run_context = extract_run_context(config)
        run_id = run_context.get("run_id", "unknown")

        # Set the current run_id for generation ID capture
        # The HTTP client will capture OpenRouter's generation ID automatically
        set_current_run_id(run_id)

        response = await model.ainvoke(messages, config)
        logger.info("[call_model] Model responded")

        # Track usage from response
        usage = extract_usage_from_response(response)

        # Debug: Log response metadata
        metadata = getattr(response, "response_metadata", None)
        usage_metadata = getattr(response, "usage_metadata", None)
        logger.info("[call_model] response_metadata: %s", metadata)
        logger.info("[call_model] usage_metadata: %s", usage_metadata)
        logger.info("[call_model] run_context: %s", run_context)

        # Costs are captured automatically at HTTP level from SSE stream
        # and recorded once at end of run in record_accumulated_usage

        if usage:
            # Get or create accumulator for this run
            if run_id not in _usage_accumulators:
                _usage_accumulators[run_id] = UsageAccumulator()

            _usage_accumulators[run_id].add(usage)
            logger.info(
                "[call_model] Usage tracked: %d tokens (run_id=%s)",
                usage.get("total_tokens", 0),
                run_id
            )
        else:
            logger.info(
                "[call_model] No usage data extracted. response_metadata keys: %s, usage_metadata: %s",
                list(metadata.keys()) if metadata else "None",
                usage_metadata
            )

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
        2. Separates tools into approval-required and non-approval batches
        3. For approval-required tools, creates interrupts and waits for responses
        4. For non-approval tools, executes them directly
        5. Returns all tool messages to continue execution
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

        # Separate tool calls into approval and non-approval batches
        approval_required_calls = []
        non_approval_calls = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")
            if should_require_approval(tool_name, tool_approvals):
                approval_required_calls.append(tool_call)
            else:
                non_approval_calls.append(tool_call)

        logger.info(
            "[approval_node] Split: %d require approval, %d do not",
            len(approval_required_calls),
            len(non_approval_calls)
        )

        # Process approval-required tools first
        for idx, tool_call in enumerate(approval_required_calls, 1):
            tool_name = tool_call.get("name")
            tool_call_id = tool_call.get("id", "unknown")

            logger.info(
                "[approval_node] [%d/%d] Processing approval-required tool: %s (id=%s)",
                idx,
                len(approval_required_calls),
                tool_name,
                tool_call_id
            )

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

        # Execute non-approval tools directly
        if non_approval_calls:
            logger.info(
                "[approval_node] Executing %d non-approval tool(s) directly: %s",
                len(non_approval_calls),
                [call.get("name") for call in non_approval_calls]
            )

            # Create temporary message with only non-approval tool calls
            temp_message = AIMessage(
                content="",
                tool_calls=non_approval_calls,
                id=last_message.id
            )
            temp_state = {"messages": [temp_message]}

            # Execute non-approval tools
            logger.info("[approval_node] Invoking tool node for non-approval tools...")
            non_approval_results = await tool_node.ainvoke(temp_state, config)

            if non_approval_results and "messages" in non_approval_results:
                num_messages = len(non_approval_results["messages"])
                logger.info(
                    "[approval_node] Non-approval tools executed, adding %d result message(s)",
                    num_messages
                )
                tool_messages.extend(non_approval_results["messages"])
            else:
                logger.warning("[approval_node] Non-approval tools returned no messages")

        logger.info(
            "[approval_node] === APPROVAL NODE COMPLETED === Returning %d message(s)",
            len(tool_messages)
        )
        return {"messages": tool_messages}

    # Function to record accumulated usage when run ends
    async def record_accumulated_usage(state: AgentState, config: RunnableConfig) -> dict:
        """Record accumulated usage to LangConnect when the run completes."""
        try:
            run_context = extract_run_context(config)
            run_id = run_context.get("run_id")

            if run_id and run_id in _usage_accumulators:
                accumulator = _usage_accumulators[run_id]
                total_usage = accumulator.get_total()

                # Get tokens from SSE capture as fallback
                captured_tokens = get_and_clear_captured_tokens(run_id)
                if captured_tokens and captured_tokens.get("total_tokens", 0) > 0:
                    if total_usage.get("total_tokens", 0) == 0:
                        total_usage["prompt_tokens"] = captured_tokens["prompt_tokens"]
                        total_usage["completion_tokens"] = captured_tokens["completion_tokens"]
                        total_usage["total_tokens"] = captured_tokens["total_tokens"]
                        logger.info(
                            "[record_accumulated_usage] Using captured tokens from SSE: %d",
                            total_usage["total_tokens"]
                        )

                # Get cost captured from SSE stream by sse_cost_capture module
                # The cost is extracted from the final SSE chunk before LangChain strips it
                # Use get_and_clear to clean up after retrieval
                captured_cost = get_and_clear_captured_cost(run_id)

                if captured_cost is not None and captured_cost > 0:
                    total_usage["cost"] = captured_cost
                    logger.info(
                        "[record_accumulated_usage] Using captured cost from SSE: $%.6f",
                        captured_cost
                    )

                # Only record if we have tokens or cost
                if total_usage.get("total_tokens", 0) > 0 or total_usage.get("cost", 0.0) > 0:
                    # Get model name: prefer captured model from SSE stream, fall back to configurable
                    # Use get_and_clear to clean up after retrieval
                    configurable = config.get("configurable", {})
                    captured_model = get_and_clear_captured_model(run_id)
                    if captured_model:
                        model_name = captured_model
                        logger.info(
                            "[record_accumulated_usage] Using captured model from SSE: %s",
                            model_name
                        )
                    else:
                        model_name = configurable.get("model_name", "unknown")

                    # Record to LangConnect
                    await record_usage(
                        thread_id=run_context.get("thread_id", "unknown"),
                        run_id=run_id,
                        model_name=model_name,
                        usage_data=total_usage,
                        user_id=run_context.get("user_id", "unknown"),
                        assistant_id=run_context.get("assistant_id"),
                        graph_name=run_context.get("graph_name", "tools_agent"),
                    )

                    logger.info(
                        "[record_accumulated_usage] Recorded usage for run %s: %d tokens, $%.6f (%d calls)",
                        run_id,
                        total_usage.get("total_tokens", 0),
                        total_usage.get("cost", 0.0),
                        total_usage.get("call_count", 0),
                    )
                else:
                    logger.warning(
                        "[record_accumulated_usage] No usage data for run %s - nothing to record",
                        run_id
                    )

                # Clean up accumulator (cost/model/tokens already cleared via get_and_clear)
                del _usage_accumulators[run_id]

        except Exception as e:
            logger.warning(f"[record_accumulated_usage] Error recording usage: {e}")

        return {"messages": []}

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

    # Build the graph
    workflow = StateGraph(effective_state_schema, config_schema=config_schema)

    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("approval", approval_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("record_usage", record_accumulated_usage)

    # Handle file attachment processing if provided
    # This allows sandbox initialization and file uploads before the agent starts
    if file_attachment_processor is not None:
        if isinstance(file_attachment_processor, tuple):
            # Two-node pattern: emit_initialization_status -> extract_file_attachments -> agent
            # This enables loading UI to appear BEFORE slow initialization starts
            emit_status_fn, extract_file_attachments_fn = file_attachment_processor
            workflow.add_node("emit_initialization_status", emit_status_fn, input_schema=effective_state_schema)
            workflow.add_node("extract_file_attachments", extract_file_attachments_fn, input_schema=effective_state_schema)
            # Note: emit_status_fn uses Command(goto="extract_file_attachments") for routing
            # So we don't add an explicit edge here - the Command handles it
            workflow.add_edge("extract_file_attachments", "agent")
            entrypoint = "emit_initialization_status"
            logger.info("[create_react_agent_with_approval] Added file attachment processing nodes (two-node pattern)")
        else:
            # Single function pattern
            workflow.add_node("extract_file_attachments", file_attachment_processor, input_schema=effective_state_schema)
            workflow.add_edge("extract_file_attachments", "agent")
            entrypoint = "extract_file_attachments"
            logger.info("[create_react_agent_with_approval] Added file attachment processing node (single-node pattern)")
    else:
        entrypoint = "agent"

    # Set entry point
    workflow.set_entry_point(entrypoint)

    # Conditional routing after agent
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "approval": "approval",
            "tools": "tools",
            END: "record_usage"  # Route to usage recording before ending
        }
    )

    # After approval, route back to agent (tool results are already in state)
    workflow.add_edge("approval", "agent")

    # After tools (no approval needed), route back to agent
    workflow.add_edge("tools", "agent")

    # After recording usage, end the graph
    workflow.add_edge("record_usage", END)

    # Compile and return
    compiled = workflow.compile()

    logger.info("[create_react_agent_with_approval] Agent graph compiled successfully")

    return compiled
