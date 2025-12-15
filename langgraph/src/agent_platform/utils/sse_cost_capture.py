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

Memory Management:
    - Entries are automatically cleaned up after TTL_SECONDS (1 hour)
    - Maximum of MAX_ENTRIES entries are kept (LRU eviction)
    - Cleanup runs periodically when new entries are added
"""

import logging
import json
import asyncio
import time
from typing import Optional
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Configuration for memory management
TTL_SECONDS = 3600  # 1 hour TTL for entries
MAX_ENTRIES = 10000  # Maximum entries before LRU eviction
CLEANUP_INTERVAL = 300  # Run cleanup every 5 minutes

# Context variable to track the current run_id
# ContextVars are async-safe and automatically scoped to the current task
_current_run_id: ContextVar[Optional[str]] = ContextVar('current_run_id', default=None)

# Lock for thread-safe access to shared dictionaries
_lock = asyncio.Lock()

# Storage for captured costs with timestamps
# Key: run_id, Value: (accumulated cost, timestamp)
_captured_costs: dict[str, tuple[float, float]] = {}

# Storage for captured model names with timestamps
# Key: run_id, Value: (model name, timestamp)
_captured_models: dict[str, tuple[str, float]] = {}

# Storage for captured token counts with timestamps
# Key: run_id, Value: (token dict, timestamp)
_captured_tokens: dict[str, tuple[dict[str, int], float]] = {}

# Track whether we've already captured cost for this chunk (avoid double-counting)
# Key: run_id, Value: (set of chunk IDs, timestamp)
_captured_cost_chunks: dict[str, tuple[set[str], float]] = {}

# Last cleanup time
_last_cleanup_time: float = 0.0


def _should_cleanup() -> bool:
    """Check if cleanup should run based on time interval."""
    global _last_cleanup_time
    now = time.time()
    return now - _last_cleanup_time > CLEANUP_INTERVAL


def _cleanup_expired_entries() -> None:
    """
    Remove expired entries from all dictionaries.

    This is called periodically to prevent memory leaks in long-running processes.
    Uses LRU eviction if MAX_ENTRIES is exceeded.
    """
    global _last_cleanup_time
    now = time.time()
    _last_cleanup_time = now

    expired_count = 0

    # Clean up costs
    expired_keys = [k for k, (_, ts) in _captured_costs.items() if now - ts > TTL_SECONDS]
    for k in expired_keys:
        del _captured_costs[k]
        expired_count += 1

    # Clean up models
    expired_keys = [k for k, (_, ts) in _captured_models.items() if now - ts > TTL_SECONDS]
    for k in expired_keys:
        del _captured_models[k]

    # Clean up tokens
    expired_keys = [k for k, (_, ts) in _captured_tokens.items() if now - ts > TTL_SECONDS]
    for k in expired_keys:
        del _captured_tokens[k]

    # Clean up chunk tracking
    expired_keys = [k for k, (_, ts) in _captured_cost_chunks.items() if now - ts > TTL_SECONDS]
    for k in expired_keys:
        del _captured_cost_chunks[k]

    # LRU eviction if still over limit
    if len(_captured_costs) > MAX_ENTRIES:
        # Sort by timestamp and remove oldest
        sorted_items = sorted(_captured_costs.items(), key=lambda x: x[1][1])
        to_remove = len(_captured_costs) - MAX_ENTRIES
        for k, _ in sorted_items[:to_remove]:
            _captured_costs.pop(k, None)
            _captured_models.pop(k, None)
            _captured_tokens.pop(k, None)
            _captured_cost_chunks.pop(k, None)
            expired_count += 1

    if expired_count > 0:
        logger.debug("[CostCapture] Cleaned up %d expired/excess entries", expired_count)


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
    entry = _captured_costs.get(run_id)
    return entry[0] if entry else None


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
    entry = _captured_costs.pop(run_id, None)
    _captured_cost_chunks.pop(run_id, None)  # Also clear chunk tracking
    if entry is not None:
        cost = entry[0]
        logger.debug("[CostCapture] Retrieved and cleared cost $%.6f for run %s", cost, run_id)
        return cost
    return None


def add_captured_cost(run_id: str, cost: float, chunk_id: Optional[str] = None) -> None:
    """
    Add cost to the captured costs for a run.

    Handles deduplication if the same chunk is processed multiple times.
    Triggers cleanup of expired entries periodically.

    Args:
        run_id: The LangGraph run ID
        cost: The cost to add (in USD)
        chunk_id: Optional ID to prevent double-counting the same chunk
    """
    now = time.time()

    # Periodic cleanup to prevent memory leaks
    if _should_cleanup():
        _cleanup_expired_entries()

    # Check for duplicate chunks
    if chunk_id:
        entry = _captured_cost_chunks.get(run_id)
        if entry is None:
            _captured_cost_chunks[run_id] = ({chunk_id}, now)
        else:
            chunks, _ = entry
            if chunk_id in chunks:
                logger.debug("[CostCapture] Skipping duplicate chunk %s", chunk_id)
                return
            chunks.add(chunk_id)
            _captured_cost_chunks[run_id] = (chunks, now)

    # Update cost with timestamp
    entry = _captured_costs.get(run_id)
    if entry is None:
        current_cost = cost
    else:
        current_cost = entry[0] + cost

    _captured_costs[run_id] = (current_cost, now)

    logger.debug(
        "[CostCapture] Added cost $%.6f for run %s (total: $%.6f)",
        cost,
        run_id,
        current_cost
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
    entry = _captured_models.get(run_id)
    return entry[0] if entry else None


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
    entry = _captured_models.pop(run_id, None)
    if entry is not None:
        model = entry[0]
        logger.debug("[CostCapture] Retrieved and cleared model '%s' for run %s", model, run_id)
        return model
    return None


def set_captured_model(run_id: str, model: str) -> None:
    """
    Set the captured model name for a run.

    Args:
        run_id: The LangGraph run ID
        model: The model name from OpenRouter
    """
    _captured_models[run_id] = (model, time.time())
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
    now = time.time()
    entry = _captured_tokens.get(run_id)

    if entry is None:
        tokens = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens}
    else:
        tokens = entry[0]
        tokens["prompt_tokens"] += prompt_tokens
        tokens["completion_tokens"] += completion_tokens
        tokens["total_tokens"] += total_tokens

    _captured_tokens[run_id] = (tokens, now)
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
    entry = _captured_tokens.pop(run_id, None)
    if entry is not None:
        tokens = entry[0]
        logger.debug(
            "[CostCapture] Retrieved and cleared tokens for run %s: %s",
            run_id,
            tokens
        )
        return tokens
    return None


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
