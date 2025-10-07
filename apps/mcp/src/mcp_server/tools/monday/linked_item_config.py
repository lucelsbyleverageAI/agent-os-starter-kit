"""Configuration loader for linked item column display settings."""

import os
import yaml
from typing import Dict, List, Optional
from ...utils.logging import get_logger

logger = get_logger(__name__)

# Path to the configuration file
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "linked_item_columns_config.yaml")

# Global config cache
_config_cache: Optional[Dict] = None


def load_linked_item_config() -> Dict:
    """Load the linked item columns configuration from YAML file."""
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    try:
        if not os.path.exists(CONFIG_PATH):
            logger.warning(f"Linked item config file not found at {CONFIG_PATH}")
            _config_cache = {}
            return _config_cache
        
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        
        logger.info(f"Loaded linked item config for {len(config)} boards")
        _config_cache = config
        return _config_cache
        
    except Exception as e:
        logger.error(f"Error loading linked item config: {str(e)}")
        _config_cache = {}
        return _config_cache


def get_board_config(board_id: str) -> Optional[Dict]:
    """Get configuration for a specific board ID."""
    config = load_linked_item_config()
    return config.get(str(board_id))


def get_board_columns(board_id: str) -> List[Dict]:
    """Get the list of columns to display for a specific board."""
    board_config = get_board_config(board_id)
    if board_config:
        return board_config.get("columns", [])
    return []


def should_include_column_for_board(board_id: str, column_id: str, column_type: str = None) -> bool:
    """
    Check if a column should be included for a specific board.
    
    Returns True if:
    1. The column is explicitly configured for this board, OR
    2. The column is a "short" type that should always be included (status, dropdown, date, etc.)
    """
    # Get configured columns for this board
    configured_columns = get_board_columns(board_id)
    configured_column_ids = [col["id"] for col in configured_columns]
    
    # Include if explicitly configured
    if column_id in configured_column_ids:
        return True
    
    # Include if it's a "short" column type that should always be shown
    short_column_types = {
        "status", "dropdown", "date", "numbers", "text", "email", "phone", 
        "link", "checkbox", "people", "rating", "formula", "auto_number", 
        "item_id", "creation_log", "last_updated", "location", "country", 
        "color_picker", "hour", "time_tracking", "week", "world_clock", 
        "button", "vote", "tags", "dependency", "progress"
    }
    
    return column_type in short_column_types


def reload_config():
    """Force reload the configuration from file."""
    global _config_cache
    _config_cache = None
    return load_linked_item_config()