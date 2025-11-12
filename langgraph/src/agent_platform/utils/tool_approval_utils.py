"""
agent_platform.utils.tool_approval_utils

Tool Approval Utilities

This module provides utility functions for implementing human-in-the-loop (HITL)
tool approval workflows in LangGraph agents. These functions enable fine-grained
control over which tool calls require human approval before execution.

Key Features:
- Check if a tool requires approval based on configuration
- Create standardized human interrupts for tool approval
- Process human responses (accept, edit, respond, ignore)
- Convert responses into appropriate tool execution or feedback

Usage Example:
    ```python
    from agent_platform.utils.tool_approval_utils import (
        should_require_approval,
        create_tool_approval_interrupt,
        process_tool_approval_response
    )

    # In your agent node
    tool_approvals = config["tool_approvals"]

    for tool_call in pending_tool_calls:
        if should_require_approval(tool_call.name, tool_approvals):
            # Create interrupt and wait for human response
            interrupt_data = create_tool_approval_interrupt(tool_call)
            response = interrupt(interrupt_data)

            # Process response and get action
            result = process_tool_approval_response(response, tool_call)
            # result will be: ToolCall (execute), ToolMessage (feedback), or None (ignore)
    ```
"""

from typing import Dict, Optional, Union, Any
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.types import interrupt

from agent_platform.types.human_interrupt import (
    HumanInterrupt,
    HumanResponse,
    ActionRequest,
    DEFAULT_FULL_CONFIG,
)
from agent_platform.sentry import get_logger

logger = get_logger(__name__)


def should_require_approval(
    tool_name: str,
    tool_approvals: Optional[Dict[str, bool]]
) -> bool:
    """
    Check if a specific tool requires human approval before execution.

    This function looks up the tool name in the approval configuration
    and returns whether approval is required. Defaults to False if the
    tool is not found in the configuration.

    Args:
        tool_name: Name of the tool to check
        tool_approvals: Dictionary mapping tool names to approval requirements
                       {tool_name: True/False}. None-safe.

    Returns:
        bool: True if the tool requires approval, False otherwise

    Examples:
        >>> approvals = {"dangerous_tool": True, "safe_tool": False}
        >>> should_require_approval("dangerous_tool", approvals)
        True
        >>> should_require_approval("safe_tool", approvals)
        False
        >>> should_require_approval("unknown_tool", approvals)
        False
        >>> should_require_approval("any_tool", None)
        False
    """
    if not tool_approvals:
        return False

    return tool_approvals.get(tool_name, False)


def create_tool_approval_interrupt(
    tool_call: Any,
    description: Optional[str] = None
) -> HumanInterrupt:
    """
    Create a human interrupt for tool approval.

    This function creates a standardized HumanInterrupt structure that
    can be passed to LangGraph's interrupt() function. The interrupt
    will pause graph execution and present the tool call to a human
    for review.

    Args:
        tool_call: The tool call object to create an interrupt for.
                  Must have 'name' and 'args' attributes.
        description: Optional markdown description providing context
                    about the tool call. If None, generates a default
                    description.

    Returns:
        HumanInterrupt: Structured interrupt data ready to pass to interrupt()

    Examples:
        >>> class ToolCall:
        ...     def __init__(self, name, args):
        ...         self.name = name
        ...         self.args = args
        >>>
        >>> tool = ToolCall("send_email", {"to": "user@example.com", "subject": "Test"})
        >>> interrupt_data = create_tool_approval_interrupt(tool)
        >>> interrupt_data["action_request"]["action"]
        'send_email'
        >>> interrupt_data["config"]["allow_edit"]
        True

    Note:
        The interrupt uses DEFAULT_FULL_CONFIG which allows all response types:
        accept, edit, respond, and ignore.
    """
    # Extract tool name and args
    tool_name = getattr(tool_call, "name", str(tool_call))
    tool_args = getattr(tool_call, "args", {})

    # Generate default description if not provided
    if description is None:
        description = f"**Tool Approval Required**\n\nThe agent wants to call `{tool_name}`.\n\nReview the arguments and choose an action."

    # Create the interrupt structure
    interrupt_data: HumanInterrupt = {
        "action_request": {
            "action": tool_name,
            "args": tool_args if isinstance(tool_args, dict) else {}
        },
        "config": DEFAULT_FULL_CONFIG,  # Allow all response types
        "description": description
    }

    logger.info(
        "[tool_approval] Created interrupt for tool: %s",
        tool_name
    )

    return interrupt_data


def process_tool_approval_response(
    response: HumanResponse,
    original_tool_call: Any
) -> Optional[Union[Any, ToolMessage]]:
    """
    Process the human response and return the appropriate action.

    This function handles all four types of human responses:
    - accept: Return the original tool call (execute as-is)
    - edit: Return a modified tool call with updated arguments
    - respond: Return a ToolMessage with human feedback for the agent
    - ignore: Return a ToolMessage indicating rejection

    Args:
        response: The HumanResponse from the interrupt, containing:
                 - type: "accept" | "edit" | "respond" | "ignore"
                 - args: Response data (varies by type)
        original_tool_call: The original tool call object that was interrupted

    Returns:
        - Tool call object (for accept/edit): Execute the tool
        - ToolMessage (for respond/ignore): Send feedback to agent
        - None: No action (should not normally happen)

    Examples:
        Accept response (execute original):
        >>> response = {"type": "accept", "args": action_request}
        >>> result = process_tool_approval_response(response, tool_call)
        >>> result == tool_call
        True

        Edit response (execute with modifications):
        >>> response = {"type": "edit", "args": {"action": "send_email", "args": {"to": "new@example.com"}}}
        >>> result = process_tool_approval_response(response, tool_call)
        >>> result.args["to"]
        'new@example.com'

        Respond response (provide feedback):
        >>> response = {"type": "respond", "args": "Please use a different subject"}
        >>> result = process_tool_approval_response(response, tool_call)
        >>> isinstance(result, ToolMessage)
        True

        Ignore response (reject):
        >>> response = {"type": "ignore", "args": None}
        >>> result = process_tool_approval_response(response, tool_call)
        >>> isinstance(result, ToolMessage)
        True
    """
    response_type = response.get("type")
    response_args = response.get("args")

    # Get tool call ID for feedback messages
    tool_call_id = getattr(original_tool_call, "id", None)
    tool_name = getattr(original_tool_call, "name", "unknown")

    logger.info(
        "[tool_approval] Processing response type=%s for tool=%s",
        response_type,
        tool_name
    )

    if response_type == "accept":
        # User approved - execute with original arguments
        logger.info("[tool_approval] Tool approved: %s", tool_name)
        return original_tool_call

    elif response_type == "edit":
        # User modified arguments - execute with new arguments
        if isinstance(response_args, dict) and "args" in response_args:
            # Update the tool call arguments
            new_args = response_args["args"]

            # Create a modified copy of the tool call
            # The exact implementation depends on your tool call structure
            # This is a generic approach that should work with most tool call objects
            try:
                # Try to create a new instance with modified args
                modified_call = type(original_tool_call)(
                    name=tool_name,
                    args=new_args,
                    id=tool_call_id
                )
                logger.info(
                    "[tool_approval] Tool arguments edited: %s",
                    tool_name
                )
                return modified_call
            except Exception:
                # Fallback: modify the original object directly
                logger.warning(
                    "[tool_approval] Could not create new tool call, modifying original"
                )
                original_tool_call.args = new_args
                return original_tool_call
        else:
            logger.warning(
                "[tool_approval] Invalid edit response format, using original"
            )
            return original_tool_call

    elif response_type == "respond":
        # User provided feedback - send as tool message
        feedback_text = response_args if isinstance(response_args, str) else str(response_args)
        feedback_message = (
            f"**Human Feedback on {tool_name}**\n\n"
            f"The user reviewed your tool call and provided this feedback:\n\n"
            f"{feedback_text}\n\n"
            f"Please consider this feedback and decide on your next action."
        )

        logger.info(
            "[tool_approval] User provided feedback for: %s",
            tool_name
        )

        return ToolMessage(
            content=feedback_message,
            tool_call_id=tool_call_id or "unknown",
            name=tool_name
        )

    elif response_type == "ignore":
        # User rejected - send rejection message
        rejection_message = (
            f"**Tool Call Rejected**\n\n"
            f"The user reviewed your request to call `{tool_name}` and decided not to proceed with this action.\n\n"
            f"Please consider an alternative approach or ask the user for clarification."
        )

        logger.info(
            "[tool_approval] Tool call rejected: %s",
            tool_name
        )

        return ToolMessage(
            content=rejection_message,
            tool_call_id=tool_call_id or "unknown",
            name=tool_name
        )

    else:
        # Unknown response type - log warning and reject
        logger.warning(
            "[tool_approval] Unknown response type: %s",
            response_type
        )
        return ToolMessage(
            content=f"Tool call could not be processed (unknown response type: {response_type})",
            tool_call_id=tool_call_id or "unknown",
            name=tool_name
        )


def get_tool_approval_config(
    config: Dict[str, Any],
    tool_source: str = "mcp"
) -> Dict[str, bool]:
    """
    Extract tool approval configuration from agent config.

    This helper function safely extracts the tool_approvals dictionary
    from either MCP or RAG configuration.

    Args:
        config: The agent configuration dictionary
        tool_source: Either "mcp" or "rag" to specify which config to check

    Returns:
        Dict[str, bool]: Tool approvals mapping, or empty dict if not found

    Examples:
        >>> config = {"mcp_config": {"tool_approvals": {"dangerous_tool": True}}}
        >>> get_tool_approval_config(config, "mcp")
        {'dangerous_tool': True}
        >>> get_tool_approval_config({}, "mcp")
        {}
    """
    if tool_source == "mcp":
        mcp_config = config.get("mcp_config")
        if mcp_config:
            return mcp_config.get("tool_approvals", {})
    elif tool_source == "rag":
        rag_config = config.get("rag")
        if rag_config:
            return rag_config.get("tool_approvals", {})

    return {}


def merge_tool_approvals(
    *approval_dicts: Optional[Dict[str, bool]]
) -> Dict[str, bool]:
    """
    Merge multiple tool approval dictionaries.

    Useful for combining approval configs from different sources
    (e.g., MCP tools + RAG tools). If a tool appears in multiple
    dictionaries, approval is required if ANY source requires it.

    Args:
        *approval_dicts: Variable number of approval dictionaries to merge

    Returns:
        Dict[str, bool]: Merged approval configuration

    Examples:
        >>> mcp_approvals = {"tool_a": True, "tool_b": False}
        >>> rag_approvals = {"tool_b": True, "tool_c": False}
        >>> merged = merge_tool_approvals(mcp_approvals, rag_approvals)
        >>> merged["tool_a"]
        True
        >>> merged["tool_b"]  # True because one source requires it
        True
        >>> merged["tool_c"]
        False
    """
    merged: Dict[str, bool] = {}

    for approval_dict in approval_dicts:
        if not approval_dict:
            continue

        for tool_name, requires_approval in approval_dict.items():
            # If any source requires approval, require it
            if requires_approval:
                merged[tool_name] = True
            elif tool_name not in merged:
                # Only set to False if not already set
                merged[tool_name] = False

    return merged
