"""
Configuration loader for collection transfer tool.

Loads environment and user mapping configurations from YAML files.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(Exception):
    """Configuration-related errors."""
    pass


class TransferConfig:
    """Manages configuration for collection transfer operations."""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize configuration loader.

        Args:
            config_dir: Path to config directory. Defaults to database/transfer_configs
        """
        if config_dir is None:
            # Default to database/transfer_configs relative to this file
            self.config_dir = Path(__file__).parent.parent / "transfer_configs"
        else:
            self.config_dir = Path(config_dir)

        if not self.config_dir.exists():
            raise ConfigError(
                f"Config directory not found: {self.config_dir}\n"
                f"Expected structure: {self.config_dir}/environments.yml and user_mappings.yml"
            )

        self.environments_file = self.config_dir / "environments.yml"
        self.user_mappings_file = self.config_dir / "user_mappings.yml"

        # Load configurations
        self._environments_config = self._load_yaml(self.environments_file)
        self._user_mappings_config = self._load_yaml(self.user_mappings_file)

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse YAML file."""
        if not file_path.exists():
            raise ConfigError(f"Config file not found: {file_path}")

        try:
            with open(file_path, "r") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse {file_path}: {e}")

    def get_environment_config(self, env_name: str) -> Dict[str, Any]:
        """
        Get database configuration for an environment.

        Args:
            env_name: Environment name (e.g., 'local', 'production')

        Returns:
            Dict with host, port, database, user, description

        Raises:
            ConfigError: If environment not found
        """
        environments = self._environments_config.get("environments", {})

        if env_name not in environments:
            available = ", ".join(environments.keys())
            raise ConfigError(
                f"Environment '{env_name}' not found in configuration.\n"
                f"Available environments: {available}\n"
                f"Check {self.environments_file}"
            )

        return environments[env_name]

    def get_connection_params(self, env_name: str) -> Dict[str, Any]:
        """
        Get database connection parameters for an environment.

        Retrieves password from environment variables in this order:
        1. POSTGRES_PASSWORD_{ENV_NAME} (e.g., POSTGRES_PASSWORD_PRODUCTION)
        2. POSTGRES_PASSWORD

        Args:
            env_name: Environment name

        Returns:
            Dict with host, port, database, user, password

        Raises:
            ConfigError: If password not found or environment not configured
        """
        config = self.get_environment_config(env_name)

        # Try environment-specific password first, then generic
        env_var_specific = f"POSTGRES_PASSWORD_{env_name.upper()}"
        password = os.getenv(env_var_specific) or os.getenv("POSTGRES_PASSWORD")

        if not password:
            raise ConfigError(
                f"Database password not found for environment '{env_name}'.\n"
                f"Set environment variable: {env_var_specific} or POSTGRES_PASSWORD"
            )

        return {
            "host": config["host"],
            "port": config["port"],
            "database": config["database"],
            "user": config["user"],
            "password": password
        }

    def get_default_source(self) -> str:
        """Get default source environment name."""
        return self._environments_config.get("defaults", {}).get("source", "local")

    def get_default_target(self) -> str:
        """Get default target environment name."""
        return self._environments_config.get("defaults", {}).get("target", "production")

    def list_environments(self) -> list[str]:
        """Get list of configured environment names."""
        return list(self._environments_config.get("environments", {}).keys())

    def get_user_mappings_config(self) -> Dict[str, Any]:
        """Get the complete user mappings configuration."""
        return self._user_mappings_config

    def get_email_mappings(self) -> list[Dict[str, str]]:
        """Get list of email mappings for documentation."""
        return self._user_mappings_config.get("email_mappings", [])

    def get_explicit_mappings(self, source_env: str, target_env: str) -> Dict[str, str]:
        """
        Get explicit UUID mappings between two environments.

        Args:
            source_env: Source environment name
            target_env: Target environment name

        Returns:
            Dict mapping source UUIDs to target UUIDs
        """
        explicit = self._user_mappings_config.get("explicit_mappings", {})
        mapping_key = f"{source_env}_to_{target_env}"
        return explicit.get(mapping_key, {})

    def get_default_owner(self, env_name: str) -> Optional[str]:
        """
        Get default owner email for an environment.

        Args:
            env_name: Environment name

        Returns:
            Email address of default owner, or None if not configured
        """
        default_owners = self._user_mappings_config.get("default_owners", {})
        return default_owners.get(env_name)

    def get_permission_strategy(self) -> Dict[str, Any]:
        """Get permission handling strategy configuration."""
        return self._user_mappings_config.get("permission_strategy", {
            "missing_user_action": "assign_to_default_owner",
            "preserve_permission_levels": True,
            "skip_system_permissions": True
        })

    def validate(self):
        """
        Validate configuration for common issues.

        Raises:
            ConfigError: If validation fails
        """
        # Check environments
        environments = self._environments_config.get("environments", {})
        if not environments:
            raise ConfigError("No environments configured in environments.yml")

        # Check required fields for each environment
        required_fields = ["host", "port", "database", "user"]
        for env_name, env_config in environments.items():
            for field in required_fields:
                if field not in env_config:
                    raise ConfigError(
                        f"Environment '{env_name}' missing required field: {field}"
                    )

        # Check default environments exist
        defaults = self._environments_config.get("defaults", {})
        if "source" in defaults and defaults["source"] not in environments:
            raise ConfigError(
                f"Default source '{defaults['source']}' not in configured environments"
            )
        if "target" in defaults and defaults["target"] not in environments:
            raise ConfigError(
                f"Default target '{defaults['target']}' not in configured environments"
            )

        # Check default owners
        default_owners = self._user_mappings_config.get("default_owners", {})
        for env_name in default_owners:
            if env_name not in environments:
                raise ConfigError(
                    f"Default owner configured for unknown environment: {env_name}"
                )

        # Validate permission strategy
        strategy = self.get_permission_strategy()
        valid_actions = ["assign_to_default_owner", "skip", "fail"]
        action = strategy.get("missing_user_action")
        if action not in valid_actions:
            raise ConfigError(
                f"Invalid missing_user_action: {action}. "
                f"Must be one of: {', '.join(valid_actions)}"
            )


def load_config(config_dir: Optional[Path] = None) -> TransferConfig:
    """
    Load and validate transfer configuration.

    Args:
        config_dir: Optional custom config directory path

    Returns:
        TransferConfig instance

    Raises:
        ConfigError: If configuration is invalid
    """
    config = TransferConfig(config_dir)
    config.validate()
    return config
