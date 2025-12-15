"""
Capture cost from OpenRouter SSE streaming responses.

OpenRouter returns cost in the final SSE chunk when `usage: { include: true }` is set,
but LangChain strips this field during response normalization.

This module intercepts the raw SSE stream to capture cost before LangChain processes it.

The cost is stored by run_id and can be retrieved after the model call completes.

Usage:
    1. Create model with cost-capturing transport (see model_utils.py)
    2. Call set_current_run_id(run_id) before model invocation
    3. After model call, use get_captured_cost(run_id) to retrieve the cost
    4. Call clear_captured_cost(run_id) after recording to free memory
"""

import logging
import json
from typing import Optional
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Context variable to track the current run_id
# ContextVars are async-safe and automatically scoped to the current task
_current_run_id: ContextVar[Optional[str]] = ContextVar('current_run_id', default=None)

# Storage for captured costs
# Key: run_id, Value: accumulated cost for that run
_captured_costs: dict[str, float] = {}

# Storage for captured model names
# Key: run_id, Value: last captured model name for that run
_captured_models: dict[str, str] = {}

# Storage for captured token counts
# Key: run_id, Value: dict with prompt_tokens, completion_tokens, total_tokens
_captured_tokens: dict[str, dict[str, int]] = {}

# Track whether we've already captured cost for this chunk (avoid double-counting)
_captured_cost_chunks: dict[str, set[str]] = {}


def set_current_run_id(run_id: str) -> None:
    """
    Set the current run ID for cost capture.

    Call this before invoking the model to associate captured costs
    with the correct run.

    Args:
        run_id: The LangGraph run ID
    """
    _current_run_id.set(run_id)
    logger.debug("[CostCapture] Set run_id: %s", run_id)


def get_current_run_id() -> Optional[str]:
    """Get the current run ID."""
    return _current_run_id.get()


def get_captured_cost(run_id: str) -> Optional[float]:
    """
    Get the captured cost for a run (without clearing).

    Args:
        run_id: The LangGraph run ID

    Returns:
        The accumulated cost in USD, or None if no cost was captured
    """
    return _captured_costs.get(run_id)


def get_and_clear_captured_cost(run_id: str) -> Optional[float]:
    """
    Get the captured cost for a run and clear it.

    Use this after each model call to get only the incremental cost
    for that specific call, preventing double-counting when recording
    to the database.

    Args:
        run_id: The LangGraph run ID

    Returns:
        The cost in USD since last clear, or None if no cost was captured
    """
    cost = _captured_costs.pop(run_id, None)
    _captured_cost_chunks.pop(run_id, None)  # Also clear chunk tracking
    if cost is not None:
        logger.debug("[CostCapture] Retrieved and cleared cost $%.6f for run %s", cost, run_id)
    return cost


def add_captured_cost(run_id: str, cost: float, chunk_id: Optional[str] = None) -> None:
    """
    Add cost to the captured costs for a run.

    Handles deduplication if the same chunk is processed multiple times.

    Args:
        run_id: The LangGraph run ID
        cost: The cost to add (in USD)
        chunk_id: Optional ID to prevent double-counting the same chunk
    """
    # Check for duplicate chunks
    if chunk_id:
        if run_id not in _captured_cost_chunks:
            _captured_cost_chunks[run_id] = set()
        if chunk_id in _captured_cost_chunks[run_id]:
            logger.debug("[CostCapture] Skipping duplicate chunk %s", chunk_id)
            return
        _captured_cost_chunks[run_id].add(chunk_id)

    if run_id not in _captured_costs:
        _captured_costs[run_id] = 0.0

    _captured_costs[run_id] += cost
    logger.debug(
        "[CostCapture] Added cost $%.6f for run %s (total: $%.6f)",
        cost,
        run_id,
        _captured_costs[run_id]
    )


def clear_captured_cost(run_id: str) -> None:
    """
    Clear captured cost, model, and tokens for a run.

    Call this after you've recorded the cost to free memory.

    Args:
        run_id: The LangGraph run ID
    """
    _captured_costs.pop(run_id, None)
    _captured_cost_chunks.pop(run_id, None)
    _captured_models.pop(run_id, None)
    _captured_tokens.pop(run_id, None)


def get_captured_model(run_id: str) -> Optional[str]:
    """
    Get the captured model name for a run (without clearing).

    Args:
        run_id: The LangGraph run ID

    Returns:
        The model name, or None if no model was captured
    """
    return _captured_models.get(run_id)


def get_and_clear_captured_model(run_id: str) -> Optional[str]:
    """
    Get the captured model name for a run and clear it.

    Use this alongside get_and_clear_captured_cost() to get the model
    that was actually used for a specific call.

    Args:
        run_id: The LangGraph run ID

    Returns:
        The model name, or None if no model was captured
    """
    model = _captured_models.pop(run_id, None)
    if model is not None:
        logger.debug("[CostCapture] Retrieved and cleared model '%s' for run %s", model, run_id)
    return model


def set_captured_model(run_id: str, model: str) -> None:
    """
    Set the captured model name for a run.

    Args:
        run_id: The LangGraph run ID
        model: The model name from OpenRouter
    """
    _captured_models[run_id] = model
    logger.debug("[CostCapture] Set model '%s' for run %s", model, run_id)


def add_captured_tokens(run_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    """
    Add token counts to the captured tokens for a run.

    Args:
        run_id: The LangGraph run ID
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_tokens: Total number of tokens
    """
    if run_id not in _captured_tokens:
        _captured_tokens[run_id] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    _captured_tokens[run_id]["prompt_tokens"] += prompt_tokens
    _captured_tokens[run_id]["completion_tokens"] += completion_tokens
    _captured_tokens[run_id]["total_tokens"] += total_tokens
    logger.debug(
        "[CostCapture] Added tokens for run %s: prompt=%d, completion=%d, total=%d",
        run_id,
        prompt_tokens,
        completion_tokens,
        total_tokens
    )


def get_and_clear_captured_tokens(run_id: str) -> Optional[dict[str, int]]:
    """
    Get the captured token counts for a run and clear them.

    Use this alongside get_and_clear_captured_cost() to get the tokens
    for a specific model call.

    Args:
        run_id: The LangGraph run ID

    Returns:
        Dict with prompt_tokens, completion_tokens, total_tokens, or None if not captured
    """
    tokens = _captured_tokens.pop(run_id, None)
    if tokens is not None:
        logger.debug(
            "[CostCapture] Retrieved and cleared tokens for run %s: %s",
            run_id,
            tokens
        )
    return tokens


def parse_sse_for_cost(sse_data: bytes) -> tuple[Optional[float], Optional[str], Optional[str], Optional[dict[str, int]]]:
    """
    Parse SSE data to extract cost, model, and tokens from the usage chunk.

    OpenRouter SSE format:
    data: {"id":"gen-xxx","model":"google/gemini-2.0-flash","choices":[{"delta":{"content":"Hello"}}]}\n\n
    data: {"id":"gen-xxx","model":"google/gemini-2.0-flash","usage":{"cost":0.00095,"prompt_tokens":194,"completion_tokens":50,"total_tokens":244}}\n\n
    data: [DONE]\n\n

    The usage data appears in the chunk that contains the "usage" field,
    typically the second-to-last chunk before [DONE].

    Args:
        sse_data: Raw SSE bytes from the stream

    Returns:
        Tuple of (cost, chunk_id, model, tokens) if found, (None, None, None, None) otherwise
        tokens is a dict with prompt_tokens, completion_tokens, total_tokens
    """
    try:
        text = sse_data.decode('utf-8')

        # Find all data: lines
        for line in text.split('\n'):
            line = line.strip()
            if not line.startswith('data: '):
                continue

            json_str = line[6:]  # Remove 'data: ' prefix

            if json_str == '[DONE]':
                continue

            try:
                data = json.loads(json_str)

                # Check if this chunk contains usage with cost
                if 'usage' in data and isinstance(data['usage'], dict):
                    usage = data['usage']
                    if 'cost' in usage:
                        cost = usage['cost']
                        chunk_id = data.get('id')  # Use generation ID as chunk ID
                        model = data.get('model')  # Extract model name
                        # Extract token counts
                        tokens = {
                            "prompt_tokens": usage.get('prompt_tokens', 0),
                            "completion_tokens": usage.get('completion_tokens', 0),
                            "total_tokens": usage.get('total_tokens', 0),
                        }
                        logger.debug(
                            "[CostCapture] Found usage in SSE chunk: $%.6f, %d tokens (id=%s, model=%s)",
                            cost,
                            tokens["total_tokens"],
                            chunk_id,
                            model
                        )
                        return float(cost), chunk_id, model, tokens

            except json.JSONDecodeError:
                # Not valid JSON, skip this line
                continue

    except Exception as e:
        logger.debug("[CostCapture] Error parsing SSE data: %s", e)

    return None, None, None, None


__all__ = [
    "set_current_run_id",
    "get_current_run_id",
    "get_captured_cost",
    "get_and_clear_captured_cost",
    "add_captured_cost",
    "clear_captured_cost",
    "get_captured_model",
    "get_and_clear_captured_model",
    "set_captured_model",
    "add_captured_tokens",
    "get_and_clear_captured_tokens",
    "parse_sse_for_cost",
]
