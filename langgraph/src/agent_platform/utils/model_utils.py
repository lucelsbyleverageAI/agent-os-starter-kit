"""
Centralized Model Configuration Utilities (OpenRouter Edition)

This module provides a single source of truth for LLM configuration across all agents
using OpenRouter as a unified API gateway for multiple model providers.

Key Features:
- Unified interface for 50+ model providers (Anthropic, OpenAI, Google, xAI, etc.)
- Single API key for all models via OpenRouter
- Automatic parameter handling (OpenRouter strips unsupported params)
- OpenRouter handles reasoning/thinking behavior with provider defaults
- Message trimming for context window management

OpenRouter Benefits:
- Single `OPENROUTER_API_KEY` for all providers
- BYOK (Bring Your Own Key) support via OpenRouter dashboard
- Centralized cost monitoring and usage tracking
- Provider-agnostic parameter handling
- Automatic reasoning behavior based on model capabilities
"""

import os
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langchain_openai import ChatOpenAI


# ============================================================================
# OpenRouter Configuration
# ============================================================================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ============================================================================
# Model Registry
# ============================================================================

class ModelTier(str, Enum):
    """Model capability tiers based on performance and cost"""
    FAST = "fast"  # Fast and economical models
    STANDARD = "standard"  # Balanced performance models
    ADVANCED = "advanced"  # High-cost, high-reasoning models


class ModelInfo(BaseModel):
    """
    Information about a specific model.

    Simplified schema for OpenRouter - provider-specific handling is done
    automatically by OpenRouter's API.
    """
    name: str
    """OpenRouter model ID (e.g., 'anthropic/claude-sonnet-4.5')"""

    display_name: str
    """Human-readable name for UI display"""

    tier: ModelTier
    """Model capability tier (FAST, STANDARD, ADVANCED)"""

    context_window: int
    """Maximum context tokens the model can process"""

    max_output_tokens: int
    """Maximum tokens the model can generate"""

    supports_reasoning: bool = False
    """
    Whether model has extended thinking/reasoning capabilities.
    When True, reasoning config is sent to OpenRouter.
    OpenRouter handles provider differences (effort vs max_tokens).
    """

    description: str = ""
    """Short description of model capabilities"""

    # Message trimming configuration (per-model defaults)
    enable_trimming: bool = True
    """Whether to enable message trimming by default"""

    trimming_max_tokens: int = 100000
    """Max tokens to keep in message history"""

    provider_preference: Optional[List[str]] = None
    """Optional list of preferred providers for OpenRouter routing (e.g., ['Groq'])"""


# Model Registry - Single source of truth for all models
# Uses OpenRouter model IDs (provider/model-name format)
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # ========== ANTHROPIC CLAUDE 4.5 ==========

    "anthropic/claude-haiku-4.5": ModelInfo(
        name="anthropic/claude-haiku-4.5",
        display_name="Claude Haiku 4.5",
        tier=ModelTier.FAST,
        context_window=200000,
        max_output_tokens=64000,
        supports_reasoning=False,
        description="Fastest Claude model with excellent cost-efficiency",
        enable_trimming=True,
        trimming_max_tokens=150000,
    ),

    "anthropic/claude-sonnet-4.5": ModelInfo(
        name="anthropic/claude-sonnet-4.5",
        display_name="Claude Sonnet 4.5",
        tier=ModelTier.STANDARD,
        context_window=200000,
        max_output_tokens=64000,
        supports_reasoning=False,
        description="Best balance of capability and speed for complex tasks",
        enable_trimming=True,
        trimming_max_tokens=150000,
    ),

    "anthropic/claude-opus-4.5": ModelInfo(
        name="anthropic/claude-opus-4.5",
        display_name="Claude Opus 4.5",
        tier=ModelTier.ADVANCED,
        context_window=200000,
        max_output_tokens=64000,
        supports_reasoning=False,
        description="Most capable Claude model for complex reasoning",
        enable_trimming=True,
        trimming_max_tokens=150000,
    ),

    # ========== OPENAI GPT ==========

    "openai/gpt-4.1-nano": ModelInfo(
        name="openai/gpt-4.1-nano",
        display_name="GPT-4.1 Nano",
        tier=ModelTier.FAST,
        context_window=1047576,
        max_output_tokens=32768,
        supports_reasoning=False,
        description="Smallest and fastest GPT-4.1 variant",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "openai/gpt-4.1-mini": ModelInfo(
        name="openai/gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        tier=ModelTier.FAST,
        context_window=1047576,
        max_output_tokens=32768,
        supports_reasoning=False,
        description="Fast and economical GPT-4.1 variant",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "openai/gpt-4.1": ModelInfo(
        name="openai/gpt-4.1",
        display_name="GPT-4.1",
        tier=ModelTier.STANDARD,
        context_window=1047576,
        max_output_tokens=32768,
        supports_reasoning=False,
        description="Full GPT-4.1 model",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "openai/gpt-5.2": ModelInfo(
        name="openai/gpt-5.2",
        display_name="GPT-5.2",
        tier=ModelTier.STANDARD,
        context_window=200000,
        max_output_tokens=100000,
        supports_reasoning=False,
        description="Latest GPT-5 series model",
        enable_trimming=True,
        trimming_max_tokens=150000,
    ),

    # ========== GOOGLE GEMINI ==========

    "google/gemini-2.5-flash-lite": ModelInfo(
        name="google/gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash Lite",
        tier=ModelTier.FAST,
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=False,
        description="Lightest Gemini model for high-throughput tasks",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "google/gemini-2.5-flash": ModelInfo(
        name="google/gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        tier=ModelTier.FAST,
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=False,
        description="Fast multimodal Gemini model",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "google/gemini-2.5-pro": ModelInfo(
        name="google/gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        tier=ModelTier.STANDARD,
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=False,
        description="Most capable Gemini multimodal model",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    # ========== XAI GROK ==========

    "x-ai/grok-4.1-fast": ModelInfo(
        name="x-ai/grok-4.1-fast",
        display_name="Grok 4.1 Fast",
        tier=ModelTier.FAST,
        context_window=131072,
        max_output_tokens=131072,
        supports_reasoning=False,
        description="Fast Grok model for quick responses",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    "x-ai/grok-4": ModelInfo(
        name="x-ai/grok-4",
        display_name="Grok 4",
        tier=ModelTier.ADVANCED,
        context_window=131072,
        max_output_tokens=131072,
        supports_reasoning=False,
        description="xAI's most advanced model",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    # ========== MOONSHOT ==========

    "moonshotai/kimi-k2-thinking": ModelInfo(
        name="moonshotai/kimi-k2-thinking",
        display_name="Kimi K2",
        tier=ModelTier.ADVANCED,
        context_window=131072,
        max_output_tokens=8192,
        supports_reasoning=False,
        description="Moonshot's Kimi K2 model",
        enable_trimming=True,
        trimming_max_tokens=100000,
    ),

    # ========== GROQ PROVIDER ==========

    "openai/gpt-oss-120b": ModelInfo(
        name="openai/gpt-oss-120b",
        display_name="GPT-OSS 120B (Groq)",
        tier=ModelTier.STANDARD,
        context_window=131072,
        max_output_tokens=8192,
        supports_reasoning=False,
        description="Open-source 120B model via Groq",
        enable_trimming=True,
        trimming_max_tokens=100000,
        provider_preference=["Groq"],
    ),
}


# =============================================================================
# Backwards Compatibility: Model Name Aliases
# =============================================================================
# Maps old model names (provider:model format) to new OpenRouter format (provider/model)
# This allows existing agent configurations to continue working without database migration

MODEL_ALIASES: Dict[str, str] = {
    # Old Anthropic format -> New OpenRouter format (colon separator)
    "anthropic:claude-sonnet-4-5-20250929": "anthropic/claude-sonnet-4.5",
    "anthropic:claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "anthropic:claude-opus-4-1-20250805": "anthropic/claude-opus-4.5",
    # Extended thinking models map to base models (reasoning enabled via supports_reasoning flag)
    "anthropic:claude-sonnet-4-5-20250929-extended-thinking": "anthropic/claude-sonnet-4.5",

    # Old registry model names -> New models (upgrade paths)
    "anthropic/claude-sonnet-4": "anthropic/claude-sonnet-4.5",
    "anthropic/claude-3.5-haiku": "anthropic/claude-haiku-4.5",
    # Old :thinking suffix maps to base model (reasoning enabled via supports_reasoning flag)
    "anthropic/claude-sonnet-4:thinking": "anthropic/claude-sonnet-4.5",
    "anthropic/claude-sonnet-4.5:thinking": "anthropic/claude-sonnet-4.5",
    "anthropic/claude-opus-4.5:thinking": "anthropic/claude-opus-4.5",

    # Old OpenAI format -> New OpenRouter format (colon separator)
    "openai:gpt-4.1-mini": "openai/gpt-4.1-mini",
    "openai:gpt-4.1-nano": "openai/gpt-4.1-nano",
    "openai:gpt-4.1": "openai/gpt-4.1",
    "openai:gpt-5": "openai/gpt-5.2",
    "openai:gpt-5.1": "openai/gpt-5.2",
    "openai:gpt-5.2": "openai/gpt-5.2",
    "openai:gpt-5-thinking": "openai/gpt-5.2",
    "openai:gpt-5.1-thinking": "openai/gpt-5.2",

    # Deprecated o3 series -> Map to gpt-5.2
    "openai/o3-mini": "openai/gpt-5.2",
    "openai/o3": "openai/gpt-5.2",

    # Legacy model names (init_chat_model format without provider prefix)
    "gpt-4.1-mini": "openai/gpt-4.1-mini",
    "gpt-4.1-nano": "openai/gpt-4.1-nano",
    "gpt-4.1": "openai/gpt-4.1",
    "gpt-5": "openai/gpt-5.2",
    "gpt-5.1": "openai/gpt-5.2",
    "gpt-5.2": "openai/gpt-5.2",

    # Old Google/xAI/Moonshot/DeepSeek -> New models (upgrade paths)
    "x-ai/grok-3-beta": "x-ai/grok-4",
    "moonshotai/kimi-k2": "moonshotai/kimi-k2-thinking",
    "deepseek/deepseek-chat": "google/gemini-2.5-flash",  # Map to similar fast model
    "deepseek/deepseek-r1": "moonshotai/kimi-k2-thinking",  # Map to similar reasoning model
}


def get_model_info(model_name: str) -> ModelInfo:
    """
    Get information about a model from the registry.

    Supports both new OpenRouter format (provider/model) and legacy formats
    (provider:model) for backwards compatibility with existing agent configurations.

    Args:
        model_name: Model identifier in either format

    Returns:
        ModelInfo object with model capabilities and limits

    Raises:
        ValueError: If model not found in registry or aliases
    """
    # Check if model is in registry directly
    if model_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_name]

    # Check aliases for backwards compatibility
    if model_name in MODEL_ALIASES:
        resolved_name = MODEL_ALIASES[model_name]
        return MODEL_REGISTRY[resolved_name]

    # Model not found
    raise ValueError(
        f"Model '{model_name}' not found in registry. "
        f"Available models: {list(MODEL_REGISTRY.keys())}"
    )


def get_models_by_tier(tier: ModelTier) -> List[ModelInfo]:
    """Get all models of a specific tier"""
    return [info for info in MODEL_REGISTRY.values() if info.tier == tier]


def get_model_options_for_ui() -> List[Dict[str, str]]:
    """
    Generate model options formatted for UI configuration.

    Returns:
        List of dicts with 'label' and 'value' keys for UI dropdowns,
        grouped by tier for better organization.
    """
    options = []

    # Group by tier for organized display
    for tier in [ModelTier.FAST, ModelTier.STANDARD, ModelTier.ADVANCED]:
        tier_models = get_models_by_tier(tier)
        for info in tier_models:
            # Extract provider from model ID for display
            provider = info.name.split('/')[0].title()
            # Clean label without tier indicator
            options.append({
                "label": f"{info.display_name} - {provider}",
                "value": info.name,
            })

    return options


# ============================================================================
# Model Initialization Configuration
# ============================================================================

class RetryConfig(BaseModel):
    """Configuration for retry logic"""
    max_retries: int = Field(default=3, ge=0, le=10)
    """Maximum number of retry attempts"""


class ReasoningConfig(BaseModel):
    """
    DEPRECATED: Reasoning configuration is no longer used.

    OpenRouter now handles reasoning automatically based on model defaults.
    This class is kept for backward compatibility only.
    """
    effort: str = Field(default="medium")
    """DEPRECATED: No longer used"""

    max_tokens: int = Field(default=8000, ge=1000)
    """DEPRECATED: No longer used"""

    exclude: bool = Field(default=False)
    """DEPRECATED: No longer used"""


class MessageTrimmingConfig(BaseModel):
    """Configuration for message history trimming"""
    enabled: bool = Field(default=True)
    """Enable automatic message trimming"""

    max_tokens: int = Field(default=100000, ge=1000)
    """Maximum tokens to keep in message history"""

    strategy: str = Field(default="last")
    """Trimming strategy: 'last' keeps recent messages, 'first' keeps earliest"""

    start_on: str = Field(default="human")
    """Message type to start the trimmed history with"""

    end_on: tuple = Field(default=("human", "tool"))
    """Message types allowed at the end of trimmed history"""

    include_system: bool = Field(default=True)
    """Always preserve system messages"""


class ModelConfig(BaseModel):
    """
    Complete configuration for model initialization.

    Simplified for OpenRouter - provider-specific handling is automatic.
    """
    model_name: str = Field(default="anthropic/claude-sonnet-4.5")
    """OpenRouter model ID to use"""

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    """Temperature for response randomness (OpenRouter strips if unsupported)"""

    max_tokens: Optional[int] = Field(default=4000)
    """Maximum tokens in model response"""

    streaming: bool = Field(default=True)
    """Enable streaming responses"""

    # Retry configuration
    retry: RetryConfig = Field(default_factory=RetryConfig)
    """Retry configuration for error handling"""

    # Message management
    trimming: Optional[MessageTrimmingConfig] = Field(default_factory=MessageTrimmingConfig)
    """Message history trimming configuration"""

    # Additional parameters
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict)
    """Additional kwargs to pass to model"""


# ============================================================================
# Model Initialization
# ============================================================================

def init_model(config: ModelConfig) -> BaseChatModel:
    """
    Initialize a chat model via OpenRouter.

    OpenRouter provides a unified API for all model providers:
    - Single API key for all models
    - Automatic parameter handling (strips unsupported params)
    - Reasoning/thinking handled automatically by OpenRouter defaults

    Args:
        config: Complete model configuration

    Returns:
        Configured ChatOpenAI instance pointing to OpenRouter

    Example:
        ```python
        from agent_platform.utils.model_utils import init_model, ModelConfig

        # Simple usage
        model = init_model(ModelConfig(
            model_name="anthropic/claude-sonnet-4.5",
            temperature=0.7
        ))

        # Use different model
        model = init_model(ModelConfig(
            model_name="openai/gpt-5.2",
            temperature=0.3
        ))
        ```
    """
    # Get model info from registry
    model_info = get_model_info(config.model_name)

    # Get API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required. "
            "Get your API key at https://openrouter.ai/keys"
        )

    # Build kwargs for ChatOpenAI with OpenRouter
    kwargs = {
        "model": model_info.name,
        "base_url": OPENROUTER_BASE_URL,
        "api_key": api_key,
        "temperature": config.temperature,  # OpenRouter strips if model doesn't support
        "max_tokens": config.max_tokens or model_info.max_output_tokens,
        "streaming": config.streaming,
        "default_headers": {
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://agent-os.app"),
            "X-Title": os.environ.get("OPENROUTER_TITLE", "Agent OS Platform"),
        },
    }

    # Initialize extra_body for additional OpenRouter parameters
    extra_body = {}

    # Apply provider preference if specified (for routing to specific providers like Groq)
    if model_info.provider_preference:
        extra_body["provider"] = {"order": model_info.provider_preference}

    # Only add extra_body if we have parameters to send
    if extra_body:
        kwargs["extra_body"] = extra_body

    # Add any extra kwargs
    kwargs.update(config.extra_kwargs)

    # Create the model
    model = ChatOpenAI(**kwargs)

    # Apply retry wrapper if configured
    if config.retry and config.retry.max_retries > 0:
        try:
            model = model.with_retry(stop_after_attempt=config.retry.max_retries)
        except Exception as e:
            # If retry setup fails, continue without it
            import warnings
            warnings.warn(f"Failed to apply retry logic: {e}")

    return model


# ============================================================================
# Message Trimming Utilities
# ============================================================================

def trim_message_history(
    messages: List[BaseMessage],
    config: MessageTrimmingConfig,
    model: Optional[BaseChatModel] = None,
) -> List[BaseMessage]:
    """
    Trim message history to fit within token limits.

    This function helps manage long conversations by intelligently trimming
    message history while preserving important context like system messages.

    Args:
        messages: List of messages to trim
        config: Trimming configuration
        model: Optional model instance for accurate token counting

    Returns:
        Trimmed list of messages
    """
    if not config.enabled:
        return messages

    # Use approximate token counting (fast and accurate enough)
    token_counter = count_tokens_approximately

    # If model is provided and supports token counting, use it
    if model is not None:
        try:
            token_counter = model
        except Exception:
            token_counter = count_tokens_approximately

    trimmed = trim_messages(
        messages,
        strategy=config.strategy,
        token_counter=token_counter,
        max_tokens=config.max_tokens,
        start_on=config.start_on,
        end_on=config.end_on,
        include_system=config.include_system,
    )

    return trimmed


def create_trimming_hook(config: MessageTrimmingConfig):
    """
    Create a pre-model hook function for automatic message trimming.

    This is useful for LangGraph agents that support pre_model_hook,
    automatically trimming messages before they're sent to the LLM.

    Args:
        config: Trimming configuration

    Returns:
        Hook function that can be passed to create_react_agent or similar
    """
    def pre_model_hook(state):
        """Trim messages before sending to model"""
        # Check llm_input_messages first (may be set by previous hooks)
        messages = state.get("llm_input_messages") or state.get("messages", [])
        trimmed_messages = trim_message_history(
            messages=messages,
            config=config,
            model=None,  # Use approximate counting in hooks for speed
        )
        return {"llm_input_messages": trimmed_messages}

    return pre_model_hook


# ============================================================================
# Quick Access Functions
# ============================================================================

def get_default_model(tier: ModelTier = ModelTier.STANDARD) -> str:
    """
    Get the default model name for a given tier.

    Args:
        tier: Model tier to get default for (FAST, STANDARD, or ADVANCED)

    Returns:
        OpenRouter model ID string
    """
    tier_models = get_models_by_tier(tier)
    if not tier_models:
        raise ValueError(f"No models found for tier: {tier}")

    # Return first model in tier (Anthropic models are listed first)
    return tier_models[0].name


def init_model_simple(
    model_name: Optional[str] = None,
) -> BaseChatModel:
    """
    Simple model initialization with sensible defaults.

    This is the recommended way to initialize models. All model-specific settings
    are configured in the registry, so users only need to select which model to use.

    Args:
        model_name: OpenRouter model ID (defaults to Claude Sonnet 4.5)

    Returns:
        Configured chat model via OpenRouter

    Example:
        ```python
        # Use default model (Claude Sonnet 4.5)
        model = init_model_simple()

        # Use specific model
        model = init_model_simple(model_name="google/gemini-2.5-pro")

        # Use GPT-5.2
        model = init_model_simple(model_name="openai/gpt-5.2")
        ```
    """
    if model_name is None:
        model_name = "anthropic/claude-sonnet-4.5"

    # Get model info for appropriate settings
    model_info = get_model_info(model_name)

    # Use sensible defaults
    config = ModelConfig(
        model_name=model_name,
        temperature=0.3,
        max_tokens=model_info.max_output_tokens,
        retry=RetryConfig(max_retries=0),  # Let OpenRouter/providers handle retries
    )

    return init_model(config)


# ============================================================================
# Backwards Compatibility
# ============================================================================

# These are kept for backwards compatibility but are no longer needed

class ModelProvider(str, Enum):
    """
    DEPRECATED: OpenRouter abstracts providers.
    Kept for backwards compatibility only.
    """
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    MOONSHOT = "moonshot"


def get_models_by_provider(provider: ModelProvider) -> List[ModelInfo]:
    """
    DEPRECATED: Use get_models_by_tier() instead.
    OpenRouter abstracts provider differences.
    """
    provider_prefix = provider.value
    return [
        info for info in MODEL_REGISTRY.values()
        if info.name.startswith(provider_prefix + "/")
    ]


def wrap_model_with_reasoning(model: BaseChatModel) -> BaseChatModel:
    """
    DEPRECATED: Reasoning is now handled via OpenRouter's unified reasoning interface.
    This function returns the model unchanged for backwards compatibility.
    """
    return model


# Backwards compatibility aliases for config classes
AnthropicCacheConfig = ReasoningConfig  # Caching handled by OpenRouter automatically
OpenAIReasoningConfig = ReasoningConfig  # Unified reasoning config
FallbackConfig = RetryConfig  # Fallbacks handled by OpenRouter's provider selection


# ============================================================================
# Export commonly used items
# ============================================================================

__all__ = [
    # Constants
    "OPENROUTER_BASE_URL",

    # Main functions
    "init_model",
    "init_model_simple",
    "trim_message_history",
    "create_trimming_hook",

    # Configuration classes
    "ModelConfig",
    "RetryConfig",
    "ReasoningConfig",
    "MessageTrimmingConfig",

    # Registry functions
    "get_model_info",
    "get_models_by_tier",
    "get_model_options_for_ui",
    "get_default_model",

    # Enums and data classes
    "ModelTier",
    "ModelInfo",

    # Registry constants
    "MODEL_REGISTRY",
    "MODEL_ALIASES",

    # Backwards compatibility
    "ModelProvider",
    "get_models_by_provider",
    "wrap_model_with_reasoning",
    "AnthropicCacheConfig",
    "OpenAIReasoningConfig",
    "FallbackConfig",
]
