"""
Utility functions for prompt construction and enhancement.
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def append_datetime_to_prompt(prompt: str, timezone: str = "Europe/London") -> str:
    """
    Appends current datetime information to a system prompt.

    This function automatically adds date and time context to agent system prompts,
    ensuring agents are aware of the current date and time without requiring
    user configuration.

    Args:
        prompt: The base system prompt to enhance
        timezone: Timezone for datetime display (default: Europe/London for GMT/BST)

    Returns:
        Enhanced prompt with datetime information appended

    Example:
        >>> base_prompt = "You are a helpful assistant."
        >>> enhanced = append_datetime_to_prompt(base_prompt)
        >>> # Returns: "You are a helpful assistant.\n\nFYI today's date & time is: Monday, January 13, 2025 at 02:30 PM GMT"
    """
    current_dt = datetime.now(ZoneInfo(timezone))
    datetime_str = current_dt.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    datetime_suffix = f"\n\nFYI today's date & time is: {datetime_str}"

    return prompt + datetime_suffix
