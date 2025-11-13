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

    def _run_one(self, call: Dict[str, Any], input_type: str, config: Dict[str, Any]) -> ToolMessage:
        """
        Execute a single tool with approval workflow.

        This method overrides ToolNode._run_one to intercept tool execution and
        check if approval is required before invoking the tool.

        Args:
            call: Tool call dictionary with name, args, id
            input_type: Type of input ("list", "dict", or "tool_calls")
            config: LangGraph RunnableConfig

        Returns:
            ToolMessage: Result of tool execution or human feedback
        """
        tool_name = call.get("name")

        logger.info(
            "[ApprovalToolNode._run_one] ✅ METHOD INVOKED! Processing tool call: name=%s, has_approval_config=%s, all_approvals=%s",
            tool_name,
            tool_name in self.tool_approvals if tool_name else False,
            list(self.tool_approvals.keys())
        )

        # Check if this tool requires approval
        if tool_name and should_require_approval(tool_name, self.tool_approvals):
            logger.info(
                "[ApprovalToolNode._run_one] Tool requires approval: %s",
                tool_name
            )

            # Create interrupt and wait for human response
            interrupt_data = create_tool_approval_interrupt(
                call,
                description=f"**Tool Approval Required**\n\nThe agent wants to call `{tool_name}`.\n\nReview the arguments and choose an action."
            )

            # This will pause execution until human responds
            human_response = interrupt(interrupt_data)

            logger.info(
                "[ApprovalToolNode._run_one] Received approval response type=%s for tool=%s",
                human_response.get("type"),
                tool_name
            )

            # Process the human response
            result = process_tool_approval_response(human_response, call)

            if isinstance(result, ToolMessage):
                # Human provided feedback or rejected - return message directly
                logger.info("[ApprovalToolNode._run_one] Returning human feedback as ToolMessage")
                return result
            elif result is None:
                # Should not happen, but handle gracefully
                logger.warning("[ApprovalToolNode._run_one] Null result from approval response")
                return ToolMessage(
                    content="Tool approval response was invalid",
                    tool_call_id=call.get("id", "unknown"),
                    name=tool_name or "unknown"
                )
            else:
                # result is a modified or original tool_call - update for execution
                call = result
                logger.info("[ApprovalToolNode._run_one] Tool approved, proceeding with execution")

        # Execute the tool using parent's _run_one method
        logger.info("[ApprovalToolNode._run_one] Executing tool: %s", tool_name)
        return super()._run_one(call, input_type, config)


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
