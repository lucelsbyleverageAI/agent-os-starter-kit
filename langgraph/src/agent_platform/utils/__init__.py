"""
agent_platform.utils

Utility modules for the agent platform.
"""

from .message_utils import clean_orphaned_tool_calls
from .model_utils import (
    # Main functions
    init_model,
    init_model_simple,
    trim_message_history,
    create_trimming_hook,
    wrap_model_with_reasoning,
    # Configuration classes
    ModelConfig,
    RetryConfig,
    FallbackConfig,
    AnthropicCacheConfig,
    OpenAIReasoningConfig,
    MessageTrimmingConfig,
    # Registry functions
    get_model_info,
    get_models_by_provider,
    get_models_by_tier,
    get_model_options_for_ui,
    get_default_model,
    # Enums and data classes
    ModelProvider,
    ModelTier,
    ModelInfo,
    # Registry constant
    MODEL_REGISTRY,
)
from .prompt_utils import append_datetime_to_prompt

__all__ = [
    "clean_orphaned_tool_calls",
    # Model utilities
    "init_model",
    "init_model_simple",
    "trim_message_history",
    "create_trimming_hook",
    "wrap_model_with_reasoning",
    "ModelConfig",
    "RetryConfig",
    "FallbackConfig",
    "AnthropicCacheConfig",
    "OpenAIReasoningConfig",
    "MessageTrimmingConfig",
    "get_model_info",
    "get_models_by_provider",
    "get_models_by_tier",
    "get_model_options_for_ui",
    "get_default_model",
    "ModelProvider",
    "ModelTier",
    "ModelInfo",
    "MODEL_REGISTRY",
    # Prompt utilities
    "append_datetime_to_prompt",
]
