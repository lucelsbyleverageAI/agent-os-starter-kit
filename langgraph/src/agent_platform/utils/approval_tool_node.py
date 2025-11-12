"""
agent_platform.utils.approval_tool_node

Tool Node with Approval Support

This module provides a custom ToolNode implementation that wraps tool execution
with human approval workflows. It intercepts tool calls, checks if approval is
required, and handles the interrupt/resume flow seamlessly.

The ApprovalToolNode acts as a drop-in replacement for LangGraph's ToolNode
while adding HITL approval capabilities.
"""

from typing import Dict, Any, Optional, List, Union, Sequence, Callable
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from agent_platform.utils.tool_approval_utils import (
    should_require_approval,
    create_tool_approval_interrupt,
    process_tool_approval_response,
)
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


class ApprovalToolNode(ToolNode):
    """
    A custom ToolNode that wraps tool execution with human approval workflows.

    This class extends LangGraph's ToolNode to add human-in-the-loop approval
    for specific tools. Tools can be configured to require human approval before
    execution, allowing fine-grained control over agent autonomy.

    The approval process:
    1. Check if tool requires approval (from tool_approvals config)
    2. If yes, create an interrupt and wait for human response
    3. Process the response (accept/edit/respond/ignore)
    4. Execute approved tools or return feedback messages

    Attributes:
        tool_approvals: Dictionary mapping tool names to approval requirements
        handle_tool_errors: Whether to catch and return tool errors as messages

    Example:
        ```python
        from agent_platform.utils.approval_tool_node import ApprovalToolNode

        # Create tool node with approval config
        tool_approvals = {"dangerous_tool": True, "safe_tool": False}
        tool_node = ApprovalToolNode(
            tools=[tool1, tool2, tool3],
            tool_approvals=tool_approvals
        )

        # Use in graph
        workflow.add_node("tools", tool_node)
        ```
    """

    def __init__(
        self,
        tools: Sequence[Union[BaseTool, Callable]],
        *,
        tool_approvals: Optional[Dict[str, bool]] = None,
        name: str = "tools",
        tags: Optional[list[str]] = None,
        handle_tool_errors: bool = True,
    ):
        """
        Initialize the ApprovalToolNode.

        Args:
            tools: List of tools that can be called
            tool_approvals: Dictionary mapping tool names to approval requirements
            name: Name of the node (default: "tools")
            tags: Optional tags for the node
            handle_tool_errors: Whether to catch and format tool errors
        """
        super().__init__(
            tools=tools,
            name=name,
            tags=tags,
            handle_tool_errors=handle_tool_errors,
        )
        self.tool_approvals = tool_approvals or {}

        logger.info(
            "[ApprovalToolNode] Initialized with %d tools, %d require approval",
            len(self.tools_by_name),
            sum(1 for v in self.tool_approvals.values() if v)
        )

    def __call__(self, state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute tools with approval workflow.

        This method intercepts tool calls from the agent, checks if they require
        approval, and handles the interrupt/resume flow as needed.

        Args:
            state: The current graph state containing messages
            config: Optional configuration (not used currently)

        Returns:
            Dict containing tool messages to add to the state
        """
        messages = state.get("messages", [])
        if not messages:
            logger.warning("[ApprovalToolNode] No messages in state")
            return {"messages": []}

        last_message = messages[-1]

        # Check if the last message has tool calls
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            logger.warning("[ApprovalToolNode] Last message has no tool calls")
            return {"messages": []}

        logger.info(
            "[ApprovalToolNode] Processing %d tool call(s)",
            len(last_message.tool_calls)
        )

        # Process each tool call
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")

            if not tool_name:
                logger.warning("[ApprovalToolNode] Tool call missing name")
                continue

            # Check if this tool requires approval
            if should_require_approval(tool_name, self.tool_approvals):
                logger.info(
                    "[ApprovalToolNode] Tool requires approval: %s",
                    tool_name
                )

                # Create interrupt and wait for human response
                interrupt_data = create_tool_approval_interrupt(
                    tool_call,
                    description=f"**Tool Approval Required**\n\nThe agent wants to call `{tool_name}`.\n\nReview the arguments and choose an action."
                )

                # This will pause execution until human responds
                human_response = interrupt(interrupt_data)

                logger.info(
                    "[ApprovalToolNode] Received approval response type=%s for tool=%s",
                    human_response.get("type"),
                    tool_name
                )

                # Process the human response
                result = process_tool_approval_response(human_response, tool_call)

                if isinstance(result, ToolMessage):
                    # Human provided feedback or rejected - add message
                    tool_messages.append(result)
                    continue
                elif result is None:
                    # Should not happen, but handle gracefully
                    logger.warning("[ApprovalToolNode] Null result from approval response")
                    continue
                else:
                    # result is a modified or original tool_call - update for execution
                    tool_call = result

            # Execute the tool (either approved or didn't need approval)
            try:
                logger.info("[ApprovalToolNode] Executing tool: %s", tool_name)

                # Create a temporary state with just this tool call for execution
                temp_state = {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    ]
                }

                # Call parent's __call__ to execute the tool
                result = super().__call__(temp_state, config)

                # Extract the tool message from the result
                result_messages = result.get("messages", [])
                if result_messages:
                    tool_messages.extend(result_messages)

            except Exception as e:
                logger.exception(
                    "[ApprovalToolNode] Error executing tool: %s",
                    tool_name
                )
                # Create error message
                error_msg = ToolMessage(
                    content=f"Error executing {tool_name}: {str(e)}",
                    tool_call_id=tool_call.get("id", "unknown"),
                    name=tool_name
                )
                tool_messages.append(error_msg)

        logger.info(
            "[ApprovalToolNode] Generated %d tool message(s)",
            len(tool_messages)
        )

        return {"messages": tool_messages}


def create_approval_tool_node(
    tools: Sequence[Union[BaseTool, Callable]],
    tool_approvals: Optional[Dict[str, bool]] = None,
    **kwargs
) -> ApprovalToolNode:
    """
    Factory function to create an ApprovalToolNode.

    This is a convenience function that matches the signature of ToolNode
    creation in LangGraph agents.

    Args:
        tools: List of tools that can be called
        tool_approvals: Dictionary mapping tool names to approval requirements
        **kwargs: Additional arguments passed to ApprovalToolNode

    Returns:
        ApprovalToolNode instance configured with the given tools and approvals

    Example:
        ```python
        tool_node = create_approval_tool_node(
            tools=[search_tool, file_tool],
            tool_approvals={"file_tool": True}
        )
        ```
    """
    return ApprovalToolNode(
        tools=tools,
        tool_approvals=tool_approvals,
        **kwargs
    )
