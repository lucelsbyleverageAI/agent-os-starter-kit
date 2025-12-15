"""
Usage Tracking Utilities for OpenRouter Cost Monitoring

This module provides utilities for capturing and recording usage data from
OpenRouter model responses. It integrates with LangConnect's usage tracking
API to enable detailed cost analysis by agent, model, and user.

Usage data is extracted from the response_metadata of AIMessages when
usage tracking is enabled in model_utils.py (via usage: { include: true }).

Key Functions:
- extract_usage_from_response: Extract usage data from an AIMessage
- record_usage: Send usage data to LangConnect API
- UsageTrackingCallback: LangChain callback for automatic tracking
- create_usage_tracking_wrapper: Wrap model calls with usage tracking
"""

import os
import logging
import asyncio
import httpx
from typing import Optional, Dict, Any, List, Union
from uuid import UUID
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


async def fetch_cost_from_openrouter(generation_id: str) -> Optional[float]:
    """
    Fetch the actual cost from OpenRouter's generation API.

    OpenRouter provides a /api/v1/generation endpoint that returns the actual
    cost for a completed generation. This is more accurate than calculating
    from token counts as it accounts for caching, promotions, and actual pricing.

    Args:
        generation_id: The generation ID from the OpenRouter response (e.g., "gen-xxx")

    Returns:
        The total cost in USD, or None if unable to fetch
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.debug("OPENROUTER_API_KEY not set, cannot fetch generation cost")
        return None

    if not generation_id:
        logger.debug("No generation_id provided, cannot fetch cost")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                # OpenRouter returns: { "data": { "total_cost": 0.00123, ... } }
                total_cost = data.get("data", {}).get("total_cost")
                if total_cost is not None:
                    logger.debug(
                        "Fetched cost from OpenRouter for %s: $%.6f",
                        generation_id,
                        total_cost
                    )
                    return float(total_cost)
                else:
                    logger.warning(
                        "OpenRouter generation response missing total_cost: %s",
                        data
                    )
                    return None
            else:
                logger.warning(
                    "Failed to fetch cost from OpenRouter: %s - %s",
                    response.status_code,
                    response.text
                )
                return None

    except Exception as e:
        logger.warning("Error fetching cost from OpenRouter: %s", e)
        return None


def extract_generation_id(response: AIMessage) -> Optional[str]:
    """
    Extract the generation ID from an AIMessage response.

    OpenRouter includes the generation ID in the response which can be used
    to fetch the actual cost via their /api/v1/generation endpoint.

    The ID may be in different locations depending on the LangChain version
    and how the response is structured.

    Args:
        response: AIMessage from model invocation

    Returns:
        Generation ID if found, None otherwise
    """
    if not hasattr(response, "response_metadata"):
        return None

    metadata = response.response_metadata
    if not metadata:
        return None

    # Try different possible locations for the ID
    # OpenRouter uses "id" at the top level of the response
    generation_id = (
        metadata.get("id") or
        metadata.get("generation_id") or
        metadata.get("request_id") or
        metadata.get("x-request-id")
    )

    if generation_id:
        logger.debug("Extracted generation_id: %s", generation_id)

    return generation_id


def extract_usage_from_response(response: AIMessage) -> Optional[Dict[str, Any]]:
    """
    Extract usage data from an AIMessage response.

    OpenRouter includes usage data in the response_metadata when
    usage: { include: true } is sent in the request.

    LangChain may put usage data in different locations depending on version:
    - response.usage_metadata (newer LangChain)
    - response.response_metadata.usage
    - response.response_metadata.token_usage

    Args:
        response: AIMessage from model invocation

    Returns:
        Dict with usage data if present, None otherwise.
        Format: {
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "cost": float  # in USD
        }
    """
    usage = None
    cost = 0.0

    # Try 1: LangChain's usage_metadata attribute (newer versions)
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        usage = {
            "prompt_tokens": getattr(um, "input_tokens", 0) or um.get("input_tokens", 0) if isinstance(um, dict) else getattr(um, "input_tokens", 0),
            "completion_tokens": getattr(um, "output_tokens", 0) or um.get("output_tokens", 0) if isinstance(um, dict) else getattr(um, "output_tokens", 0),
            "total_tokens": getattr(um, "total_tokens", 0) or um.get("total_tokens", 0) if isinstance(um, dict) else getattr(um, "total_tokens", 0),
        }
        # Normalize field names (LangChain uses input_tokens/output_tokens)
        if isinstance(um, dict):
            usage["prompt_tokens"] = um.get("input_tokens", um.get("prompt_tokens", 0))
            usage["completion_tokens"] = um.get("output_tokens", um.get("completion_tokens", 0))
            usage["total_tokens"] = um.get("total_tokens", usage["prompt_tokens"] + usage["completion_tokens"])

    # Try 2: response_metadata (standard location)
    if not usage or usage.get("total_tokens", 0) == 0:
        metadata = getattr(response, "response_metadata", None) or {}

        # Check various keys where LangChain might put usage
        usage_data = (
            metadata.get("usage") or
            metadata.get("token_usage") or
            metadata.get("openai", {}).get("usage") if isinstance(metadata.get("openai"), dict) else None or
            {}
        )

        if usage_data:
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", usage_data.get("input_tokens", 0)),
                "completion_tokens": usage_data.get("completion_tokens", usage_data.get("output_tokens", 0)),
                "total_tokens": usage_data.get("total_tokens", 0),
            }
            if usage["total_tokens"] == 0:
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

            # Get cost from usage data or metadata
            cost = usage_data.get("cost", 0.0)

        # Cost might be at top level of metadata
        if cost == 0.0:
            cost = metadata.get("cost", 0.0)

    if not usage or usage.get("total_tokens", 0) == 0:
        return None

    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cost": float(cost) if cost else 0.0,
    }


# Retry configuration for usage recording
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 4.0


async def record_usage(
    thread_id: str,
    run_id: str,
    model_name: str,
    usage_data: Dict[str, Any],
    user_id: str,
    assistant_id: Optional[str] = None,
    graph_name: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
) -> bool:
    """
    Record usage data to LangConnect API with retry logic.

    This function sends usage data to the LangConnect /usage/record endpoint
    for persistent storage and later aggregation. Implements exponential
    backoff retry to handle transient failures.

    Args:
        thread_id: Thread ID for the conversation
        run_id: LangGraph run ID
        model_name: OpenRouter model ID used
        usage_data: Dict with prompt_tokens, completion_tokens, total_tokens, cost
        user_id: User ID who initiated the run
        assistant_id: Optional assistant instance ID
        graph_name: Optional agent template name
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        True if recording succeeded, False otherwise
    """
    langconnect_url = os.environ.get("LANGCONNECT_URL", "http://localhost:8080")
    service_key = os.environ.get("LANGCONNECT_SERVICE_ACCOUNT_KEY")

    if not service_key:
        logger.warning("LANGCONNECT_SERVICE_ACCOUNT_KEY not set, skipping usage recording")
        return False

    payload = {
        "thread_id": thread_id,
        "run_id": run_id,
        "model_name": model_name,
        "prompt_tokens": usage_data.get("prompt_tokens", 0),
        "completion_tokens": usage_data.get("completion_tokens", 0),
        "total_tokens": usage_data.get("total_tokens", 0),
        "cost": usage_data.get("cost", 0.0),
    }

    if assistant_id:
        payload["assistant_id"] = assistant_id
    if graph_name:
        payload["graph_name"] = graph_name

    last_error: Optional[Exception] = None
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{langconnect_url}/usage/record",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {service_key}",
                        "Content-Type": "application/json",
                        "X-User-Id": user_id,  # Pass user context
                    },
                    timeout=10.0,
                )

                if response.status_code in [200, 201]:
                    if attempt > 0:
                        logger.info(
                            f"Recorded usage for run {run_id} after {attempt} retries"
                        )
                    else:
                        logger.debug(
                            f"Recorded usage for run {run_id}: {usage_data.get('total_tokens', 0)} tokens, ${usage_data.get('cost', 0.0):.6f}"
                        )
                    return True

                # Don't retry on client errors (4xx) except 429 (rate limit)
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    logger.warning(
                        f"Failed to record usage (client error): {response.status_code} - {response.text}"
                    )
                    return False

                # Server error or rate limit - retry with backoff
                last_error = Exception(f"HTTP {response.status_code}: {response.text}")

        except httpx.TimeoutException as e:
            last_error = e
            logger.debug(f"Timeout recording usage (attempt {attempt + 1}/{max_retries + 1}): {e}")

        except httpx.ConnectError as e:
            last_error = e
            logger.debug(f"Connection error recording usage (attempt {attempt + 1}/{max_retries + 1}): {e}")

        except Exception as e:
            last_error = e
            logger.debug(f"Error recording usage (attempt {attempt + 1}/{max_retries + 1}): {e}")

        # If not the last attempt, sleep with exponential backoff
        if attempt < max_retries:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    # All retries exhausted
    logger.warning(
        f"Failed to record usage for run {run_id} after {max_retries + 1} attempts. "
        f"Last error: {last_error}. Usage data: {usage_data.get('total_tokens', 0)} tokens, "
        f"${usage_data.get('cost', 0.0):.6f}"
    )
    return False


class UsageAccumulator:
    """
    Accumulates usage data across multiple model calls within a single run.

    This is useful for agents that make multiple model calls (e.g., tool loops)
    and need to track total usage for the entire run.

    Usage:
        accumulator = UsageAccumulator()

        # After each model call
        usage = extract_usage_from_response(response)
        if usage:
            accumulator.add(usage)

        # At end of run
        total = accumulator.get_total()
        await record_usage(..., usage_data=total, ...)
    """

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cost = 0.0
        self.call_count = 0

    def add(self, usage: Dict[str, Any]) -> None:
        """Add usage data from a single model call."""
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)
        self.cost += usage.get("cost", 0.0)
        self.call_count += 1

    def get_total(self) -> Dict[str, Any]:
        """Get accumulated usage data."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "call_count": self.call_count,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cost = 0.0
        self.call_count = 0


def get_model_from_response(response: AIMessage) -> Optional[str]:
    """
    Extract the model name from an AIMessage response.

    Args:
        response: AIMessage from model invocation

    Returns:
        Model name if present in metadata, None otherwise
    """
    if not hasattr(response, "response_metadata"):
        return None

    metadata = response.response_metadata
    if not metadata:
        return None

    # OpenRouter includes model in metadata
    return metadata.get("model") or metadata.get("model_name")


class UsageTrackingCallback(BaseCallbackHandler):
    """
    LangChain callback handler for automatic usage tracking.

    This callback captures usage data from LLM responses and records it
    to LangConnect for cost analysis.

    IMPORTANT: To prevent double-recording of costs, choose ONE of these patterns:

    Pattern 1 - Manual recording (recommended for agents with complex flows):
        callback = UsageTrackingCallback(..., auto_record=False)
        model.invoke(messages, config={"callbacks": [callback]})
        # At end of agent run, record accumulated usage once:
        await record_usage(..., usage_data=callback.get_accumulated_usage())

    Pattern 2 - Auto recording (simpler, but can cause double-counting if
                combined with manual record_usage() calls):
        callback = UsageTrackingCallback(..., auto_record=True)
        model.invoke(messages, config={"callbacks": [callback]})
        # Usage is recorded automatically after each LLM call

    WARNING: If auto_record=True, do NOT also call record_usage() manually
    for the same run_id/model_name, as this will result in costs being
    accumulated twice in the database.

    Usage:
        callback = UsageTrackingCallback(
            thread_id="...",
            run_id="...",
            user_id="...",
            model_name="anthropic/claude-sonnet-4.5",
            assistant_id="...",
            graph_name="tools_agent",
            auto_record=False  # Recommended default
        )

        # Use with model invocation
        model.invoke(messages, config={"callbacks": [callback]})

        # Access accumulated usage and record manually
        total_usage = callback.get_accumulated_usage()
    """

    def __init__(
        self,
        thread_id: str,
        run_id: str,
        user_id: str,
        model_name: str,
        assistant_id: Optional[str] = None,
        graph_name: Optional[str] = None,
        auto_record: bool = False,
    ):
        """
        Initialize the usage tracking callback.

        Args:
            thread_id: Thread ID for the conversation
            run_id: LangGraph run ID
            user_id: User ID who initiated the run
            model_name: Default model name (can be overridden from response)
            assistant_id: Optional assistant instance ID
            graph_name: Optional agent template name
            auto_record: If True, automatically record usage after each LLM call
        """
        super().__init__()
        self.thread_id = thread_id
        self.run_id = run_id
        self.user_id = user_id
        self.model_name = model_name
        self.assistant_id = assistant_id
        self.graph_name = graph_name
        self.auto_record = auto_record
        self.accumulator = UsageAccumulator()

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM finishes generating."""
        try:
            # Extract usage from response
            if response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage")
                if usage:
                    usage_data = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "cost": usage.get("cost", 0.0),
                    }
                    self.accumulator.add(usage_data)

                    # Get model from response if available
                    model = response.llm_output.get("model") or response.llm_output.get("model_name") or self.model_name

                    if self.auto_record:
                        # Record asynchronously without blocking.
                        # Use done callback to log any errors from the background task.
                        task = asyncio.create_task(self._record_usage(model, usage_data))
                        task.add_done_callback(self._handle_record_task_result)

        except Exception as e:
            logger.warning(f"Error in usage tracking callback: {e}")

    def _handle_record_task_result(self, task: asyncio.Task) -> None:
        """Handle completion of background usage recording task."""
        try:
            # This will raise if the task failed
            task.result()
        except asyncio.CancelledError:
            logger.debug("Usage recording task was cancelled")
        except Exception as e:
            logger.warning(
                f"Background usage recording failed for run {self.run_id}: {e}"
            )

    async def _record_usage(self, model_name: str, usage_data: Dict[str, Any]) -> None:
        """Record usage data asynchronously."""
        await record_usage(
            thread_id=self.thread_id,
            run_id=self.run_id,
            model_name=model_name,
            usage_data=usage_data,
            user_id=self.user_id,
            assistant_id=self.assistant_id,
            graph_name=self.graph_name,
        )

    def get_accumulated_usage(self) -> Dict[str, Any]:
        """Get total accumulated usage across all LLM calls."""
        return self.accumulator.get_total()


def extract_run_context(config: RunnableConfig) -> Dict[str, Any]:
    """
    Extract run context from RunnableConfig.

    This extracts thread_id, run_id, user_id, and other context
    from the LangGraph configuration.

    Args:
        config: RunnableConfig from LangGraph

    Returns:
        Dict with extracted context values
    """
    context = {}

    # Extract from configurable
    configurable = config.get("configurable", {})
    metadata = config.get("metadata", {})

    # Debug log to understand config structure
    logger.debug(
        "[extract_run_context] config keys: %s, configurable keys: %s, metadata keys: %s",
        list(config.keys()) if config else "None",
        list(configurable.keys()) if configurable else "None",
        list(metadata.keys()) if metadata else "None",
    )

    # Thread ID
    thread_id = configurable.get("thread_id")
    if thread_id:
        context["thread_id"] = str(thread_id) if isinstance(thread_id, UUID) else thread_id

    # Run ID - check multiple possible locations where LangGraph might put it
    run_id = (
        config.get("run_id") or
        configurable.get("run_id") or
        configurable.get("langgraph_run_id") or
        metadata.get("run_id") or
        metadata.get("langgraph_run_id")
    )
    if run_id:
        context["run_id"] = str(run_id) if isinstance(run_id, UUID) else run_id

    # User ID - typically in x-user-id header or configurable
    user_id = configurable.get("user_id") or configurable.get("x-user-id")
    if user_id:
        context["user_id"] = user_id

    # Assistant ID
    assistant_id = configurable.get("assistant_id")
    if assistant_id:
        context["assistant_id"] = str(assistant_id) if isinstance(assistant_id, UUID) else assistant_id

    # Graph name
    graph_name = configurable.get("graph_name") or configurable.get("langgraph_node")
    if graph_name:
        context["graph_name"] = graph_name

    return context


def create_usage_tracking_callback(
    config: RunnableConfig,
    model_name: str,
    auto_record: bool = False,
) -> Optional[UsageTrackingCallback]:
    """
    Create a usage tracking callback from RunnableConfig.

    This is a convenience function that extracts context from the config
    and creates a properly configured callback.

    Args:
        config: RunnableConfig from LangGraph
        model_name: Model name being used
        auto_record: If True, automatically record usage after each call.
                     Default is False to prevent double-recording when
                     combined with manual record_usage() calls.

    Returns:
        UsageTrackingCallback if context is available, None otherwise
    """
    context = extract_run_context(config)

    # Need at least thread_id, run_id, and user_id to record
    if not all(k in context for k in ["thread_id", "run_id", "user_id"]):
        logger.debug("Insufficient context for usage tracking, skipping")
        return None

    return UsageTrackingCallback(
        thread_id=context["thread_id"],
        run_id=context["run_id"],
        user_id=context["user_id"],
        model_name=model_name,
        assistant_id=context.get("assistant_id"),
        graph_name=context.get("graph_name"),
        auto_record=auto_record,
    )


async def track_usage_from_messages(
    messages: List[BaseMessage],
    config: RunnableConfig,
    model_name: str,
) -> None:
    """
    Extract and record usage from a list of messages.

    This scans the messages for AIMessages with usage metadata and
    records the accumulated usage.

    Args:
        messages: List of messages to scan
        config: RunnableConfig for context
        model_name: Default model name
    """
    context = extract_run_context(config)

    if not all(k in context for k in ["thread_id", "run_id", "user_id"]):
        logger.debug("Insufficient context for usage tracking, skipping")
        return

    accumulator = UsageAccumulator()

    for message in messages:
        if isinstance(message, AIMessage):
            usage = extract_usage_from_response(message)
            if usage:
                accumulator.add(usage)
                # Try to get model from response
                response_model = get_model_from_response(message)
                if response_model:
                    model_name = response_model

    total = accumulator.get_total()
    if total["total_tokens"] > 0:
        await record_usage(
            thread_id=context["thread_id"],
            run_id=context["run_id"],
            model_name=model_name,
            usage_data=total,
            user_id=context["user_id"],
            assistant_id=context.get("assistant_id"),
            graph_name=context.get("graph_name"),
        )


__all__ = [
    "fetch_cost_from_openrouter",
    "extract_generation_id",
    "extract_usage_from_response",
    "record_usage",
    "UsageAccumulator",
    "get_model_from_response",
    "UsageTrackingCallback",
    "extract_run_context",
    "create_usage_tracking_callback",
    "track_usage_from_messages",
]
