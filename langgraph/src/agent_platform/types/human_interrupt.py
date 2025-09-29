"""
agent_platform.types.human_interrupt

Human Interrupt Schema Models

This module defines the Pydantic models for human-in-the-loop interrupts compatible
with the Agent Inbox UI. These models define the structure for pausing agent execution,
presenting information to humans, and handling their responses.

The schema supports four types of human responses:
- accept: Approve the proposed action as-is
- edit: Modify the action arguments before execution
- ignore: Skip the action entirely
- response: Provide textual feedback to the agent

Key Features:
- Agent Inbox UI compatibility
- Type-safe interrupt/response handling
- Flexible action configuration
- Reusable across multiple agent types
"""

from typing_extensions import TypedDict
from typing import Literal, Optional, Union


class HumanInterruptConfig(TypedDict):
    """
    Configuration for what actions are allowed in response to a human interrupt.
    
    This determines which response options are presented to the human in the
    Agent Inbox UI. At least one option must be enabled.
    
    Attributes:
        allow_ignore: Whether the human can skip/ignore the action
        allow_respond: Whether the human can provide textual feedback
        allow_edit: Whether the human can modify the action arguments
        allow_accept: Whether the human can approve the action as-is
    """
    allow_ignore: bool
    allow_respond: bool
    allow_edit: bool
    allow_accept: bool


class ActionRequest(TypedDict):
    """
    Represents an action (typically a tool call) that requires human review.
    
    This structure encapsulates the action name and its parameters, providing
    the human with complete context about what the agent wants to do.
    
    Attributes:
        action: The name of the action/tool to be executed
        args: Dictionary of arguments for the action
    """
    action: str
    args: dict


class HumanInterrupt(TypedDict):
    """
    Complete interrupt request sent to the Agent Inbox for human review.
    
    This structure is passed to LangGraph's interrupt() function to pause
    execution and request human input. It includes the proposed action,
    configuration options, and descriptive context.
    
    Attributes:
        action_request: The action requiring human review
        config: Configuration for allowed response types
        description: Optional markdown description providing context
    """
    action_request: ActionRequest
    config: HumanInterruptConfig
    description: Optional[str]


class HumanResponse(TypedDict):
    """
    Response from human after reviewing an interrupt.
    
    This structure is returned by LangGraph's interrupt() function after
    a human provides input through the Agent Inbox UI.
    
    Attributes:
        type: The type of response chosen by the human
        args: Response data, varies by type:
            - accept: ActionRequest (same as original)
            - edit: ActionRequest (with modified args)
            - response: str (textual feedback)
            - ignore: None
    """
    type: Literal['accept', 'ignore', 'response', 'edit']
    args: Union[None, str, ActionRequest]


# Default configurations for common use cases
DEFAULT_FULL_CONFIG: HumanInterruptConfig = {
    "allow_ignore": True,
    "allow_respond": True,
    "allow_edit": True,
    "allow_accept": True,
}

DEFAULT_APPROVE_ONLY_CONFIG: HumanInterruptConfig = {
    "allow_ignore": True,
    "allow_respond": False,
    "allow_edit": False,
    "allow_accept": True,
}

DEFAULT_EDIT_CONFIG: HumanInterruptConfig = {
    "allow_ignore": True,
    "allow_respond": True,
    "allow_edit": True,
    "allow_accept": False,
} 