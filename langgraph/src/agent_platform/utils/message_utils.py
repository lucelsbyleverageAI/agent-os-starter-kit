from typing import List
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_core.messages.utils import filter_messages
import logging

logger = logging.getLogger(__name__)


def clean_orphaned_tool_calls(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Remove AI messages with tool calls that have no corresponding tool messages,
    and tool messages that have no corresponding AI message tool calls.
    
    This prevents OpenAI API errors that occur when an AI message with tool_calls
    is not followed by corresponding ToolMessage responses. This commonly happens
    during human-in-the-loop interrupts where tool calls are approved/rejected
    but never executed.
    
    Args:
        messages: List of BaseMessage objects to clean
        
    Returns:
        List of BaseMessage objects with orphaned tool calls removed
        
    Example:
        >>> from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
        >>> messages = [
        ...     HumanMessage(content="Calculate 2+2"),
        ...     AIMessage(content="", tool_calls=[{"id": "call_123", "name": "calc", "args": {}}]),
        ...     HumanMessage(content="Actually never mind")  # No ToolMessage response!
        ... ]
        >>> cleaned = clean_orphaned_tool_calls(messages)
        >>> # The AIMessage with orphaned tool_calls will be removed
    """
    if not messages:
        return messages
    
    logger.debug("[CLEAN_MESSAGES] start count=%s", len(messages))
    
    # Step 1: Identify all tool call IDs and their states
    tool_call_ids_made = set()  # Tool calls made by AI messages
    tool_call_ids_responded = set()  # Tool calls that got responses
    
    # Step 2: Scan messages to build the state
    for i, message in enumerate(messages):
        if isinstance(message, AIMessage) and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_call_ids_made.add(tool_call["id"])
            logger.debug("[CLEAN_MESSAGES] ai_message_with_tool_calls index=%s count=%s", i, len(message.tool_calls))
        elif isinstance(message, ToolMessage):
            tool_call_ids_responded.add(message.tool_call_id)
            logger.debug("[CLEAN_MESSAGES] tool_response index=%s call_id=%s", i, message.tool_call_id)
    
    # Step 3: Find orphaned tool call IDs
    orphaned_tool_call_ids = tool_call_ids_made - tool_call_ids_responded
    orphaned_tool_message_ids = tool_call_ids_responded - tool_call_ids_made
    
    all_orphaned_ids = orphaned_tool_call_ids | orphaned_tool_message_ids
    
    
    # Step 4: Use LangChain's filter_messages to clean up if needed
    if all_orphaned_ids:    
        logger.debug("[CLEAN_MESSAGES] filtering_orphans count=%s", len(all_orphaned_ids))
        cleaned_messages = filter_messages(
            messages, 
            exclude_tool_calls=list(all_orphaned_ids)
        )
        logger.debug("[CLEAN_MESSAGES] filtered from=%s to=%s", len(messages), len(cleaned_messages))
        return cleaned_messages
    
    logger.debug("[CLEAN_MESSAGES] no_orphans=true")
    return messages 