"""
Metadata validation utilities for detecting and fixing corrupted JSONB data.

This module provides defensive parsing for metadata/config/context fields that
may have been corrupted by double JSON encoding or character array conversion.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Maximum reasonable size for metadata/config/context fields (100KB)
MAX_FIELD_SIZE_BYTES = 100_000


def is_character_indexed_dict(obj: Any) -> bool:
    """
    Detect if an object is a character-indexed dictionary.

    Character-indexed dicts occur when a JSON string is iterated and stored
    character-by-character: {"0": "{", "1": "\"", "2": "k", ...}

    Args:
        obj: Object to check

    Returns:
        True if obj is a character-indexed dict
    """
    if not isinstance(obj, dict):
        return False

    # Check if all keys are sequential string integers starting from "0"
    keys = sorted(obj.keys())
    if not keys:
        return False

    # Must start with "0"
    if keys[0] != "0":
        return False

    # Check first 10 keys are sequential (performance optimization)
    check_limit = min(10, len(keys))
    for i in range(check_limit):
        if str(i) not in obj:
            return False
        # Values should be single characters (strings of length 1)
        if not isinstance(obj[str(i)], str):
            return False

    return True


def reconstruct_from_character_indexed(char_dict: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Reconstruct original JSON object from character-indexed dictionary.

    Args:
        char_dict: Character-indexed dictionary {"0": "x", "1": "y", ...}

    Returns:
        Reconstructed dict, or None if reconstruction fails
    """
    try:
        # Reconstruct JSON string from character indices
        chars = []
        for i in range(len(char_dict)):
            key = str(i)
            if key not in char_dict:
                log.warning(f"Missing character index {i} during reconstruction")
                return None
            chars.append(char_dict[key])

        json_str = ''.join(chars)

        # Parse reconstructed JSON string
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        log.warning(f"Failed to reconstruct from character-indexed dict: {e}")
        return None


def parse_metadata_safe(metadata: Any, field_name: str = "metadata") -> Dict[str, Any]:
    """
    Safely parse metadata that may be corrupted or in various formats.

    Handles:
    - Already parsed dicts (pass through)
    - JSON strings (parse once)
    - Double-encoded JSON strings (parse twice)
    - Character-indexed dicts (reconstruct and parse)
    - Corrupted/invalid data (return empty dict with warning)

    Args:
        metadata: Metadata in unknown format
        field_name: Field name for logging (e.g., "metadata", "config")

    Returns:
        Parsed metadata dict (empty dict if parsing fails)
    """
    # Already a dict - check for character-indexed corruption
    if isinstance(metadata, dict):
        if is_character_indexed_dict(metadata):
            log.warning(f"{field_name} is character-indexed dict, attempting reconstruction")
            reconstructed = reconstruct_from_character_indexed(metadata)
            if reconstructed:
                log.info(f"Successfully reconstructed {field_name} from character indices")
                return reconstructed
            else:
                log.error(f"Failed to reconstruct {field_name}, returning empty dict")
                return {}
        else:
            # Normal dict, return as-is
            return metadata

    # String - try to parse as JSON (may be single or double-encoded)
    if isinstance(metadata, str):
        # Check size before parsing
        if len(metadata) > MAX_FIELD_SIZE_BYTES:
            log.error(f"{field_name} string is too large ({len(metadata)} bytes), possible corruption")
            return {}

        # Try parsing once (normal case)
        try:
            parsed = json.loads(metadata)

            # If result is a dict, we're done
            if isinstance(parsed, dict):
                return parsed

            # If result is still a string, try parsing again (double-encoded)
            if isinstance(parsed, str):
                log.warning(f"{field_name} was double-encoded JSON string, parsing twice")
                try:
                    double_parsed = json.loads(parsed)
                    if isinstance(double_parsed, dict):
                        return double_parsed
                except (json.JSONDecodeError, ValueError):
                    log.error(f"Failed to parse double-encoded {field_name}")
                    return {}

            # Result is neither dict nor string (unexpected)
            log.warning(f"{field_name} parsed to unexpected type: {type(parsed)}")
            return {}

        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"Failed to parse {field_name} JSON string: {e}")
            return {}

    # None or other type - return empty dict
    if metadata is None:
        return {}

    log.warning(f"{field_name} has unexpected type: {type(metadata)}, returning empty dict")
    return {}


def validate_field_size(obj: Any, field_name: str, max_size: int = MAX_FIELD_SIZE_BYTES) -> Tuple[bool, Optional[str]]:
    """
    Validate that a field is not suspiciously large (indicates corruption).

    Args:
        obj: Object to check size
        field_name: Field name for error messages
        max_size: Maximum allowed size in bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Serialize to JSON to check size
        json_str = json.dumps(obj)
        size_bytes = len(json_str.encode('utf-8'))

        if size_bytes > max_size:
            error = f"{field_name} is too large ({size_bytes} bytes, max {max_size}), possible corruption"
            log.error(error)
            return False, error

        return True, None
    except (TypeError, ValueError) as e:
        error = f"Failed to validate {field_name} size: {e}"
        log.error(error)
        return False, error


def sanitize_langgraph_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a payload before sending to LangGraph API.

    Ensures metadata, config, and context fields are properly formatted dicts
    and not corrupted strings or character arrays.

    Args:
        payload: Payload to sanitize

    Returns:
        Sanitized payload with validated fields
    """
    sanitized = payload.copy()

    # Sanitize metadata
    if "metadata" in sanitized:
        sanitized["metadata"] = parse_metadata_safe(sanitized["metadata"], "metadata")
        valid, error = validate_field_size(sanitized["metadata"], "metadata")
        if not valid:
            log.warning(f"Metadata validation failed: {error}, using empty dict")
            sanitized["metadata"] = {}

    # Sanitize config
    if "config" in sanitized:
        original_config = sanitized["config"]
        if isinstance(original_config, str):
            sanitized["config"] = parse_metadata_safe(original_config, "config")
        elif isinstance(original_config, dict) and is_character_indexed_dict(original_config):
            sanitized["config"] = parse_metadata_safe(original_config, "config")
        # Validate size
        if "config" in sanitized:
            valid, error = validate_field_size(sanitized["config"], "config")
            if not valid:
                log.warning(f"Config validation failed: {error}, using empty dict")
                sanitized["config"] = {}

    # Sanitize context
    if "context" in sanitized:
        original_context = sanitized["context"]
        if isinstance(original_context, str):
            sanitized["context"] = parse_metadata_safe(original_context, "context")
        elif isinstance(original_context, dict) and is_character_indexed_dict(original_context):
            sanitized["context"] = parse_metadata_safe(original_context, "context")
        # Validate size
        if "context" in sanitized:
            valid, error = validate_field_size(sanitized["context"], "context")
            if not valid:
                log.warning(f"Context validation failed: {error}, using empty dict")
                sanitized["context"] = {}

    return sanitized
