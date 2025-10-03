"""
Centralized Model Configuration Utilities

This module provides a single source of truth for LLM configuration across all agents,
including model registry, retry/fallback logic, provider-specific optimizations, and
message trimming functionality.

Key Features:
- Centralized model registry for easy updates when new models are released
- Production-grade retry and fallback logic using LangChain's built-in functionality
- Provider-specific optimizations (Anthropic prompt caching, OpenAI reasoning models)
- Message trimming to manage context windows
- Consistent configuration across all agents
"""

from typing import Optional, List, Literal, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI


# ============================================================================
# Model Registry
# ============================================================================

class ModelProvider(str, Enum):
    """Supported model providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class ModelTier(str, Enum):
    """Model capability tiers based on performance and cost"""
    FAST = "fast"  # Fast and economical models
    STANDARD = "standard"  # Balanced performance models
    ADVANCED = "advanced"  # High-cost, high-reasoning models


class ModelInfo(BaseModel):
    """Information about a specific model"""
    name: str
    display_name: str
    provider: ModelProvider
    tier: ModelTier
    context_window: int
    max_output_tokens: int
    supports_tool_calling: bool = True
    supports_streaming: bool = True
    supports_caching: bool = False  # Anthropic prompt caching
    is_reasoning_model: bool = False  # OpenAI reasoning models (o1, o3, etc.)
    supports_extended_thinking: bool = False  # Claude extended thinking
    description: str = ""
    
    # Message trimming configuration (per-model defaults)
    enable_trimming: bool = True  # Whether to enable trimming by default
    trimming_max_tokens: int = 100000  # Max tokens to keep in history


# Model Registry - Single source of truth for all models
# Models are organized by tier: Fast (cheap/quick), Standard (balanced), Advanced (high-reasoning)
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # ========== FAST TIER: Quick and economical models ==========
    
    # Anthropic Fast
    "anthropic:claude-3-5-haiku-latest": ModelInfo(
        name="anthropic:claude-3-5-haiku-latest",
        display_name="Claude 3.5 Haiku",
        provider=ModelProvider.ANTHROPIC,
        tier=ModelTier.FAST,
        context_window=200000,
        max_output_tokens=8192,
        supports_caching=True,
        description="Fast and economical with prompt caching",
        enable_trimming=True,
        trimming_max_tokens=150000,  # Conservative for 200k context window
    ),
    
    # OpenAI Fast
    "openai:gpt-4.1-mini": ModelInfo(
        name="gpt-4.1-mini",  # Just model name, no provider prefix
        display_name="GPT-4.1 Mini",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.FAST,
        context_window=128000,
        max_output_tokens=16384,
        description="Fast and economical GPT-4.1 variant",
        enable_trimming=True,
        trimming_max_tokens=100000,  # Conservative for 128k context
    ),
    "openai:gpt-4.1-nano": ModelInfo(
        name="gpt-4.1-nano",  # Just model name, no provider prefix
        display_name="GPT-4.1 Nano",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.FAST,
        context_window=128000,
        max_output_tokens=16384,
        description="Ultra-fast and economical variant",
        enable_trimming=True,
        trimming_max_tokens=100000,  # Conservative for 128k context
    ),
    "openai:gpt-5-mini": ModelInfo(
        name="gpt-5-mini",  # Just model name, no provider prefix
        display_name="GPT-5 Mini",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.FAST,
        context_window=128000,
        max_output_tokens=65536,
        is_reasoning_model=True,
        description="Fast reasoning model for coding tasks",
        enable_trimming=True,
        trimming_max_tokens=100000,  # Leave room for reasoning tokens
    ),
    "openai:gpt-5-nano": ModelInfo(
        name="gpt-5-nano",  # Just model name, no provider prefix
        display_name="GPT-5 Nano",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.FAST,
        context_window=128000,
        max_output_tokens=65536,
        is_reasoning_model=True,
        description="Economical reasoning model",
        enable_trimming=True,
        trimming_max_tokens=100000,  # Leave room for reasoning tokens
    ),
    
    # ========== STANDARD TIER: Balanced performance models ==========
    
    # Anthropic Standard
    "anthropic:claude-sonnet-4-5-20250929": ModelInfo(
        name="anthropic:claude-sonnet-4-5-20250929",
        display_name="Claude Sonnet 4.5",
        provider=ModelProvider.ANTHROPIC,
        tier=ModelTier.STANDARD,
        context_window=200000,
        max_output_tokens=64000,
        supports_caching=True,
        description="Best model for complex agents and coding",
        enable_trimming=True,
        trimming_max_tokens=150000,  # Conservative for 200k context
    ),
    
    # OpenAI Standard
    "openai:gpt-4.1": ModelInfo(
        name="gpt-4.1",  # Just model name, no provider prefix for direct API calls
        display_name="GPT-4.1",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.STANDARD,
        context_window=128000,
        max_output_tokens=16384,
        description="Latest GPT-4 model",
        enable_trimming=True,
        trimming_max_tokens=100000,  # Conservative for 128k context
    ),
    "openai:gpt-5": ModelInfo(
        name="gpt-5",  # Just model name, no provider prefix for direct API calls
        display_name="GPT-5",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.STANDARD,
        context_window=200000,
        max_output_tokens=100000,
        is_reasoning_model=True,
        description="Advanced reasoning model",
        enable_trimming=True,
        trimming_max_tokens=150000,  # Leave room for reasoning tokens
    ),
    
    # ========== ADVANCED TIER: High-cost, high-reasoning models ==========
    
    # Anthropic Advanced
    "anthropic:claude-opus-4-1-20250805": ModelInfo(
        name="anthropic:claude-opus-4-1-20250805",
        display_name="Claude Opus 4.1",
        provider=ModelProvider.ANTHROPIC,
        tier=ModelTier.ADVANCED,
        context_window=200000,
        max_output_tokens=32000,
        supports_caching=True,
        description="Exceptional model for specialized complex tasks",
        enable_trimming=True,
        trimming_max_tokens=150000,  # Conservative for 200k context
    ),
    "anthropic:claude-sonnet-4-5-20250929-extended-thinking": ModelInfo(
        name="anthropic:claude-sonnet-4-5-20250929",  # Same underlying model
        display_name="Claude Sonnet 4.5 (Extended Thinking)",
        provider=ModelProvider.ANTHROPIC,
        tier=ModelTier.ADVANCED,
        context_window=200000,
        max_output_tokens=64000,
        supports_caching=True,
        supports_extended_thinking=True,  # Enable extended thinking
        description="Claude Sonnet 4.5 with extended thinking enabled for complex reasoning",
        enable_trimming=True,
        trimming_max_tokens=120000,  # Lower to leave room for thinking tokens (2000 budget)
    ),
    
    # OpenAI Advanced
    "openai:gpt-5-thinking": ModelInfo(
        name="gpt-5",  # Same underlying model, no provider prefix
        display_name="GPT-5 (Thinking Mode)",
        provider=ModelProvider.OPENAI,
        tier=ModelTier.ADVANCED,
        context_window=200000,
        max_output_tokens=100000,
        is_reasoning_model=True,
        description="GPT-5 with enhanced thinking for complex reasoning tasks",
        enable_trimming=True,
        trimming_max_tokens=120000,  # Lower to leave room for reasoning tokens
    ),
}


def get_model_info(model_name: str) -> ModelInfo:
    """
    Get information about a model from the registry.
    
    Args:
        model_name: Full model identifier (e.g., "anthropic:claude-3-7-sonnet-latest")
        
    Returns:
        ModelInfo object with model capabilities and limits
        
    Raises:
        ValueError: If model not found in registry
    """
    if model_name not in MODEL_REGISTRY:
        raise ValueError(
            f"Model '{model_name}' not found in registry. "
            f"Available models: {list(MODEL_REGISTRY.keys())}"
        )
    return MODEL_REGISTRY[model_name]


def get_models_by_provider(provider: ModelProvider) -> List[ModelInfo]:
    """Get all models for a specific provider"""
    return [info for info in MODEL_REGISTRY.values() if info.provider == provider]


def get_models_by_tier(tier: ModelTier) -> List[ModelInfo]:
    """Get all models of a specific tier"""
    return [info for info in MODEL_REGISTRY.values() if info.tier == tier]


def get_model_options_for_ui() -> List[Dict[str, str]]:
    """
    Generate model options formatted for UI configuration.
    
    Returns:
        List of dicts with 'label' and 'value' keys for UI dropdowns
        The 'value' is the registry key (unique), not the model name
    """
    return [
        {
            "label": f"{info.display_name} ({info.tier.value})",
            "value": registry_key,  # Use registry key for uniqueness
        }
        for registry_key, info in MODEL_REGISTRY.items()
    ]


# ============================================================================
# Model Initialization Configuration
# ============================================================================

class RetryConfig(BaseModel):
    """Configuration for retry logic"""
    max_retries: int = Field(default=3, ge=0, le=10)
    """Maximum number of retry attempts"""
    
    retry_on_timeout: bool = Field(default=True)
    """Retry on timeout errors"""
    
    retry_on_rate_limit: bool = Field(default=True)
    """Retry on rate limit errors"""
    
    exponential_backoff: bool = Field(default=True)
    """Use exponential backoff between retries"""
    
    max_retry_delay: float = Field(default=60.0)
    """Maximum delay between retries in seconds"""


class FallbackConfig(BaseModel):
    """Configuration for fallback models"""
    enabled: bool = Field(default=False)
    """Enable fallback to alternative models on failure"""
    
    fallback_models: List[str] = Field(default_factory=list)
    """List of model names to try in order if primary fails"""
    
    fallback_on_errors: List[str] = Field(
        default_factory=lambda: ["rate_limit", "timeout", "server_error"]
    )
    """Error types that trigger fallback"""


class AnthropicCacheConfig(BaseModel):
    """Configuration for Anthropic prompt caching"""
    enabled: bool = Field(default=True)
    """Enable prompt caching to reduce costs on repeated context"""
    
    min_cache_tokens: int = Field(default=1024, ge=1024)
    """Minimum tokens to cache (Anthropic requires >= 1024)"""
    
    cache_system_prompt: bool = Field(default=True)
    """Cache the system prompt"""
    
    cache_recent_messages: int = Field(default=0, ge=0)
    """Number of recent messages to cache (0 = none)"""


class OpenAIReasoningConfig(BaseModel):
    """Configuration for OpenAI reasoning models (o-series, GPT-5)"""
    enabled: bool = Field(default=True)
    """Enable reasoning model specific features"""
    
    reasoning_effort: Literal["low", "medium", "high"] = Field(default="medium")
    """
    Reasoning effort level:
    - low: Fast, economical, fewer reasoning tokens
    - medium: Balanced speed and reasoning quality
    - high: Maximum reasoning quality, slower and more expensive
    """
    
    reasoning_summary: Literal["detailed", "auto", "none"] = Field(default="auto")
    """
    Reasoning summary verbosity:
    - detailed: Full reasoning summary
    - auto: Automatic summary based on context
    - none: No reasoning summary
    """
    
    max_output_tokens: Optional[int] = Field(default=None)
    """Max tokens for both reasoning and output combined"""


class MessageTrimmingConfig(BaseModel):
    """Configuration for message history trimming"""
    enabled: bool = Field(default=True)
    """Enable automatic message trimming"""
    
    max_tokens: int = Field(default=100000, ge=1000)
    """Maximum tokens to keep in message history"""
    
    strategy: Literal["last", "first"] = Field(default="last")
    """
    Trimming strategy:
    - last: Keep the most recent messages
    - first: Keep the earliest messages
    """
    
    start_on: Literal["human", "ai"] = Field(default="human")
    """Message type to start the trimmed history with"""
    
    end_on: tuple = Field(default=("human", "tool"))
    """Message types allowed at the end of trimmed history"""
    
    include_system: bool = Field(default=True)
    """Always preserve system messages"""
    
    token_counter: Optional[Any] = Field(default=None)
    """Custom token counter (defaults to approximate counting)"""


class ModelConfig(BaseModel):
    """
    Complete configuration for model initialization.
    
    This is the main configuration class that combines all model settings,
    retry/fallback logic, and provider-specific optimizations.
    """
    model_name: str = Field(default="anthropic:claude-3-7-sonnet-latest")
    """Primary model to use"""
    
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    """Temperature for response randomness (0=deterministic, 2=creative)"""
    
    max_tokens: Optional[int] = Field(default=4000)
    """Maximum tokens in model response"""
    
    streaming: bool = Field(default=True)
    """Enable streaming responses"""
    
    # Retry and Fallback
    retry: RetryConfig = Field(default_factory=RetryConfig)
    """Retry configuration for error handling"""
    
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)
    """Fallback model configuration"""
    
    # Provider-specific configs
    anthropic_cache: Optional[AnthropicCacheConfig] = Field(default_factory=AnthropicCacheConfig)
    """Anthropic prompt caching configuration"""
    
    openai_reasoning: Optional[OpenAIReasoningConfig] = Field(default_factory=OpenAIReasoningConfig)
    """OpenAI reasoning model configuration"""
    
    # Message management
    trimming: Optional[MessageTrimmingConfig] = Field(default_factory=MessageTrimmingConfig)
    """Message history trimming configuration"""
    
    # Additional model parameters
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict)
    """Additional provider-specific kwargs to pass to model"""


# ============================================================================
# Model Initialization
# ============================================================================

def _apply_retry_logic(model: BaseChatModel, retry_config: RetryConfig) -> BaseChatModel:
    """
    Apply retry logic to a model using LangChain's built-in with_retry.
    
    Args:
        model: Base chat model instance
        retry_config: Retry configuration
        
    Returns:
        Model wrapped with retry logic
    """
    if retry_config.max_retries == 0:
        return model
    
    # LangChain's with_retry() uses a simpler interface
    # It only accepts stop_after_attempt parameter
    # The exponential backoff is built-in by default
    try:
        return model.with_retry(stop_after_attempt=retry_config.max_retries)
    except Exception as e:
        # If with_retry fails, return the model without retry wrapper
        # This ensures the agent still works even if retry setup fails
        import warnings
        warnings.warn(f"Failed to apply retry logic: {e}. Model will run without retry wrapper.")
        return model


def _apply_fallback_logic(
    model: BaseChatModel,
    fallback_config: FallbackConfig,
    config: ModelConfig,
) -> BaseChatModel:
    """
    Apply fallback logic to a model using LangChain's built-in with_fallbacks.
    
    Args:
        model: Primary chat model instance
        fallback_config: Fallback configuration
        config: Full model configuration for creating fallback models
        
    Returns:
        Model wrapped with fallback logic
    """
    if not fallback_config.enabled or not fallback_config.fallback_models:
        return model
    
    # Create fallback model instances
    fallback_models = []
    for fallback_model_name in fallback_config.fallback_models:
        try:
            # Create a simplified config for fallback models
            fallback_model_config = config.model_copy(deep=True)
            fallback_model_config.model_name = fallback_model_name
            fallback_model_config.fallback.enabled = False  # Prevent nested fallbacks
            
            fallback_model = init_model(fallback_model_config)
            fallback_models.append(fallback_model)
        except Exception as e:
            print(f"Warning: Failed to initialize fallback model {fallback_model_name}: {e}")
    
    if fallback_models:
        return model.with_fallbacks(fallback_models)
    
    return model


def _apply_anthropic_caching(
    model: BaseChatModel,
    cache_config: AnthropicCacheConfig,
    model_info: ModelInfo,
) -> BaseChatModel:
    """
    Apply Anthropic prompt caching configuration.
    
    Anthropic prompt caching can significantly reduce costs by caching
    repeated context (system prompts, documents, etc.).
    
    Args:
        model: ChatAnthropic instance
        cache_config: Caching configuration
        model_info: Model information from registry
        
    Returns:
        Model configured with caching parameters
    """
    if not cache_config.enabled or not model_info.supports_caching:
        return model
    
    if not isinstance(model, ChatAnthropic):
        return model
    
    # Anthropic caching is controlled via message metadata
    # This is handled at the message level, not model initialization
    # We store the config on the model for later use
    model._cache_config = cache_config
    
    return model


def _apply_openai_reasoning_config(
    model: BaseChatModel,
    reasoning_config: OpenAIReasoningConfig,
    model_info: ModelInfo,
) -> BaseChatModel:
    """
    Apply OpenAI reasoning model configuration.
    
    OpenAI reasoning models (o-series, GPT-5) require special handling:
    1. Must use Responses API (output_version="responses/v1")
    2. Reasoning parameters are passed at invoke time, not init time
    3. We store the config on the model for later use by agents
    
    Args:
        model: ChatOpenAI instance
        reasoning_config: Reasoning configuration
        model_info: Model information from registry
        
    Returns:
        Model with reasoning config stored for invoke-time use
        
    Note:
        The actual reasoning parameters must be passed when invoking:
        model.invoke("...", reasoning={"effort": "medium", "summary": "auto"})
    """
    if not reasoning_config.enabled or not model_info.is_reasoning_model:
        return model
    
    if not isinstance(model, ChatOpenAI):
        return model
    
    # Store reasoning config on model for later use at invoke time
    # This allows agents to automatically apply reasoning parameters
    model._reasoning_config = reasoning_config
    
    return model


def init_model(config: ModelConfig) -> BaseChatModel:
    """
    Initialize a chat model with all production-grade enhancements.
    
    This is the main function to use for creating LLM instances across
    all agents. It handles:
    - Model initialization from registry
    - Retry logic for transient failures
    - Fallback to alternative models
    - Provider-specific optimizations (caching, reasoning)
    - Message trimming configuration
    
    Args:
        config: Complete model configuration
        
    Returns:
        Fully configured chat model instance
        
    Example:
        ```python
        from agent_platform.utils.model_utils import init_model, ModelConfig
        
        # Simple usage
        model = init_model(ModelConfig(
            model_name="anthropic:claude-3-7-sonnet-latest",
            temperature=0.7
        ))
        
        # With fallback and retry
        model = init_model(ModelConfig(
            model_name="anthropic:claude-3-7-sonnet-latest",
            retry=RetryConfig(max_retries=3),
            fallback=FallbackConfig(
                enabled=True,
                fallback_models=["anthropic:claude-3-5-sonnet-latest"]
            )
        ))
        ```
    """
    # Get model info from registry
    model_info = get_model_info(config.model_name)
    
    # OpenAI reasoning models - use standard initialization
    # Note: Reasoning parameters are passed at invoke time via reasoning={...}
    # The "responses/v1" API is triggered automatically when using reasoning params
    if model_info.provider == ModelProvider.OPENAI and model_info.is_reasoning_model:
        # Build kwargs for ChatOpenAI directly
        openai_kwargs = {
            "model": model_info.name,
            "max_retries": 2,
        }
        
        # Don't set temperature for reasoning models (they use fixed temperature)
        
        if config.max_tokens:
            openai_kwargs["max_tokens"] = config.max_tokens
        
        if config.streaming and model_info.supports_streaming:
            openai_kwargs["streaming"] = True
        
        # Add extra kwargs
        openai_kwargs.update(config.extra_kwargs)
        
        # Directly instantiate ChatOpenAI
        model = ChatOpenAI(**openai_kwargs)
    else:
        # Use init_chat_model for all other models (Anthropic, non-reasoning OpenAI)
        init_kwargs = {
            "model": model_info.name,  # Use actual API model name, not registry key
        }
        
        # Set temperature (will be overridden for extended thinking models)
        if not model_info.is_reasoning_model:
            init_kwargs["temperature"] = config.temperature
        
        if config.max_tokens:
            init_kwargs["max_tokens"] = config.max_tokens
        
        if config.streaming and model_info.supports_streaming:
            init_kwargs["streaming"] = True
        
        # Claude extended thinking configuration
        # Must be passed at model initialization for ChatAnthropic
        # IMPORTANT: When thinking is enabled, temperature MUST be 1.0
        if model_info.provider == ModelProvider.ANTHROPIC and model_info.supports_extended_thinking:
            init_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 2000,  # Token budget for thinking process
            }
            # Override temperature to 1.0 (required by Claude for extended thinking)
            init_kwargs["temperature"] = 1.0
        
        # Add extra provider-specific kwargs
        init_kwargs.update(config.extra_kwargs)
        
        # Initialize the base model
        model = init_chat_model(**init_kwargs)
    
    # Apply retry logic
    if config.retry:
        model = _apply_retry_logic(model, config.retry)
    
    # Apply fallback logic
    if config.fallback:
        model = _apply_fallback_logic(model, config.fallback, config)
    
    # Apply provider-specific configurations
    if model_info.provider == ModelProvider.ANTHROPIC and config.anthropic_cache:
        model = _apply_anthropic_caching(model, config.anthropic_cache, model_info)
    
    if model_info.provider == ModelProvider.OPENAI and config.openai_reasoning:
        model = _apply_openai_reasoning_config(model, config.openai_reasoning, model_info)
    
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
        
    Example:
        ```python
        from agent_platform.utils.model_utils import (
            trim_message_history,
            MessageTrimmingConfig
        )
        
        trimmed = trim_message_history(
            messages=state["messages"],
            config=MessageTrimmingConfig(
                max_tokens=100000,
                strategy="last",
                start_on="human",
            )
        )
        ```
    """
    if not config.enabled:
        return messages
    
    # Use provided token counter or default to approximate
    token_counter = config.token_counter or count_tokens_approximately
    
    # If model is provided and supports token counting, use it
    if model is not None:
        try:
            token_counter = model
        except Exception:
            # Fall back to approximate counting
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
        
    Example:
        ```python
        from agent_platform.utils.model_utils import (
            create_trimming_hook,
            MessageTrimmingConfig
        )
        from langgraph.prebuilt import create_react_agent
        
        trimming_hook = create_trimming_hook(
            MessageTrimmingConfig(max_tokens=100000)
        )
        
        agent = create_react_agent(
            model=model,
            tools=tools,
            pre_model_hook=trimming_hook,
        )
        ```
    """
    def pre_model_hook(state):
        """Trim messages before sending to model"""
        trimmed_messages = trim_message_history(
            messages=state["messages"],
            config=config,
            model=None,  # Use approximate counting in hooks for speed
        )
        # Return under llm_input_messages to avoid modifying original state
        return {"llm_input_messages": trimmed_messages}
    
    return pre_model_hook


def wrap_model_with_reasoning(model: BaseChatModel) -> BaseChatModel:
    """
    Wrap an OpenAI reasoning model to automatically apply reasoning parameters.
    
    For OpenAI reasoning models (o-series, GPT-5), the reasoning parameters
    must be passed at invoke time. This wrapper automatically applies them
    based on the stored config.
    
    Args:
        model: ChatOpenAI instance with _reasoning_config attribute
        
    Returns:
        Wrapped model that automatically applies reasoning parameters
        
    Example:
        ```python
        model = init_model_simple(model_name="openai:gpt-5")
        wrapped_model = wrap_model_with_reasoning(model)
        
        # Reasoning parameters automatically applied
        response = wrapped_model.invoke("What is 2+2?")
        ```
    
    Note:
        This is optional - you can also manually pass reasoning params:
        model.invoke("...", reasoning={"effort": "medium", "summary": "auto"})
    """
    if not hasattr(model, '_reasoning_config'):
        return model
    
    if not isinstance(model, ChatOpenAI):
        return model
    
    reasoning_config = model._reasoning_config
    
    # Create wrapper that adds reasoning params
    original_invoke = model.invoke
    
    def invoke_with_reasoning(input, **kwargs):
        # Only add reasoning if not already provided
        if 'reasoning' not in kwargs:
            reasoning_params = {
                "effort": reasoning_config.reasoning_effort,
            }
            
            # Only include summary if not "none"
            if reasoning_config.reasoning_summary != "none":
                reasoning_params["summary"] = reasoning_config.reasoning_summary
            
            kwargs['reasoning'] = reasoning_params
        
        return original_invoke(input, **kwargs)
    
    model.invoke = invoke_with_reasoning
    
    return model


# ============================================================================
# Quick Access Functions
# ============================================================================

def get_default_model(tier: ModelTier = ModelTier.STANDARD) -> str:
    """
    Get the default model name for a given tier.
    
    Args:
        tier: Model tier to get default for (FAST, STANDARD, or ADVANCED)
        
    Returns:
        Model name string
    """
    tier_models = get_models_by_tier(tier)
    if not tier_models:
        raise ValueError(f"No models found for tier: {tier}")
    
    # Prefer Anthropic models as default
    anthropic_models = [m for m in tier_models if m.provider == ModelProvider.ANTHROPIC]
    if anthropic_models:
        return anthropic_models[0].name
    
    return tier_models[0].name


def init_model_simple(
    model_name: Optional[str] = None,
) -> BaseChatModel:
    """
    Simple model initialization with sensible defaults.
    
    This is the recommended way to initialize models. All model-specific settings
    (temperature, max_tokens, etc.) are configured in the model registry, so users
    only need to select which model to use.
    
    Note: Retry logic is disabled because it interferes with tool binding.
    LangGraph and provider SDKs have their own retry mechanisms.
    
    Args:
        model_name: Model to use (defaults to standard tier). 
                   If None, uses Claude Sonnet 4.5.
        
    Returns:
        Configured chat model with optimal settings for that model
        
    Example:
        ```python
        # Use default model (Claude Sonnet 4.5)
        model = init_model_simple()
        
        # Use specific model
        model = init_model_simple(
            model_name="anthropic:claude-3-5-haiku-latest"
        )
        ```
    """
    if model_name is None:
        model_name = get_default_model(ModelTier.STANDARD)
    
    # Get model info to use appropriate settings
    model_info = get_model_info(model_name)
    
    # Set defaults based on model tier
    if model_info.tier == ModelTier.FAST:
        temperature = 0.3
        max_tokens = 4000
    elif model_info.tier == ModelTier.STANDARD:
        temperature = 0.3
        max_tokens = 8000
    else:  # ADVANCED
        temperature = 0.3
        max_tokens = 16000
    
    config = ModelConfig(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        retry=RetryConfig(max_retries=3), 
        fallback=FallbackConfig(enabled=False),
    )
    
    return init_model(config)


# ============================================================================
# Export commonly used items
# ============================================================================

__all__ = [
    # Main functions
    "init_model",
    "init_model_simple",
    "trim_message_history",
    "create_trimming_hook",
    "wrap_model_with_reasoning",
    
    # Configuration classes
    "ModelConfig",
    "RetryConfig",
    "FallbackConfig",
    "AnthropicCacheConfig",
    "OpenAIReasoningConfig",
    "MessageTrimmingConfig",
    
    # Registry functions
    "get_model_info",
    "get_models_by_provider",
    "get_models_by_tier",
    "get_model_options_for_ui",
    "get_default_model",
    
    # Enums and data classes
    "ModelProvider",
    "ModelTier",
    "ModelInfo",
    
    # Registry constant
    "MODEL_REGISTRY",
]

