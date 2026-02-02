"""
Configuration management with YAML and environment variable support.

Environment variables take precedence over YAML configuration.
Sensitive values are automatically masked in logs.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from secretary.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Patterns for sensitive keys that should be masked in logs
SENSITIVE_PATTERNS = [
    re.compile(r".*api[_-]?key.*", re.IGNORECASE),
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r".*password.*", re.IGNORECASE),
    re.compile(r".*credential.*", re.IGNORECASE),
]

# Default configuration paths
DEFAULT_CONFIG_PATHS = [
    Path("secretary.yaml"),
    Path("secretary.yml"),
    Path("config/secretary.yaml"),
    Path.home() / ".secretary" / "config.yaml",
]


def _is_sensitive_key(key: str) -> bool:
    """Check if a key contains sensitive information."""
    return any(pattern.match(key) for pattern in SENSITIVE_PATTERNS)


def _mask_value(value: Any) -> str:
    """Mask sensitive values for logging."""
    if value is None:
        return "None"
    str_value = str(value)
    if len(str_value) <= 8:
        return "***"
    return f"{str_value[:4]}...{str_value[-4:]}"


class Config:
    """
    YAML + environment variable integrated configuration management.

    Environment variables take precedence over YAML values.
    Supports nested key access with dot notation (e.g., "adapters.gmail.enabled").

    Usage:
        config = Config()
        api_key = config.anthropic_api_key
        gmail_enabled = config.get("adapters.gmail.enabled", default=True)
    """

    def __init__(self, config_path: Path | str | None = None, env_file: Path | str | None = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to YAML config file. If None, searches default locations.
            env_file: Path to .env file. If None, searches current directory.
        """
        # Load environment variables from .env file
        env_path = Path(env_file) if env_file else None
        load_dotenv(dotenv_path=env_path, override=False)

        self._config: dict[str, Any] = {}
        self._config_path: Path | None = None

        # Load YAML configuration
        self._load_yaml(config_path)

        logger.debug("Configuration initialized from: %s", self._config_path or "defaults only")

    def _load_yaml(self, config_path: Path | str | None = None) -> None:
        """Load YAML configuration file."""
        if config_path:
            path = Path(config_path)
            if not path.exists():
                raise ConfigurationError(f"Configuration file not found: {path}")
            self._config_path = path
        else:
            # Search default locations
            for default_path in DEFAULT_CONFIG_PATHS:
                if default_path.exists():
                    self._config_path = default_path
                    break

        if self._config_path:
            try:
                with self._config_path.open("r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        self._config = loaded
                logger.info("Loaded configuration from: %s", self._config_path)
            except yaml.YAMLError as e:
                raise ConfigurationError(f"Invalid YAML in {self._config_path}: {e}") from e
            except OSError as e:
                raise ConfigurationError(f"Failed to read {self._config_path}: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Environment variables take precedence over YAML.
        Supports dot notation for nested keys (e.g., "adapters.gmail.enabled").

        Environment variable mapping:
            "adapters.gmail.enabled" -> SECRETARY_ADAPTERS_GMAIL_ENABLED

        Args:
            key: Configuration key (dot notation supported)
            default: Default value if key not found

        Returns:
            Configuration value
        """
        # Check environment variable first
        env_key = f"SECRETARY_{key.upper().replace('.', '_')}"
        env_value = os.getenv(env_key)

        if env_value is not None:
            # Convert string to appropriate type
            value = self._parse_env_value(env_value)
            if _is_sensitive_key(key):
                logger.debug("Config %s from env: %s", key, _mask_value(value))
            else:
                logger.debug("Config %s from env: %s", key, value)
            return value

        # Fall back to YAML config
        value = self._get_nested(key)
        if value is not None:
            if _is_sensitive_key(key):
                logger.debug("Config %s from yaml: %s", key, _mask_value(value))
            else:
                logger.debug("Config %s from yaml: %s", key, value)
            return value

        return default

    def _get_nested(self, key: str) -> Any:
        """Get nested value from config dict using dot notation."""
        parts = key.split(".")
        value = self._config

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None

        return value

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """Parse environment variable string to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False

        # Integer
        try:
            return int(value)
        except ValueError:
            pass

        # Float
        try:
            return float(value)
        except ValueError:
            pass

        # String
        return value

    @property
    def anthropic_api_key(self) -> str | None:
        """Get Anthropic API key from environment."""
        key = os.getenv("ANTHROPIC_API_KEY")
        if key:
            logger.debug("Anthropic API key found: %s", _mask_value(key))
        return key

    @property
    def github_token(self) -> str | None:
        """Get GitHub token from environment or file."""
        token = os.getenv("GITHUB_TOKEN")
        if token:
            logger.debug("GitHub token from env: %s", _mask_value(token))
            return token

        # Fall back to token file
        token_file = Path(r"C:\claude\json\github_token.txt")
        if token_file.exists():
            try:
                token = token_file.read_text(encoding="utf-8").strip()
                logger.debug("GitHub token from file: %s", _mask_value(token))
                return token
            except OSError:
                pass

        return None

    @property
    def google_credentials_path(self) -> Path:
        """Get Google OAuth credentials path."""
        return Path(r"C:\claude\json\desktop_credentials.json")

    @property
    def gmail_token_path(self) -> Path:
        """Get Gmail token path."""
        return Path(r"C:\claude\json\token_gmail.json")

    @property
    def calendar_token_path(self) -> Path:
        """Get Calendar token path."""
        return Path(r"C:\claude\json\token_calendar.json")

    @property
    def slack_credentials_path(self) -> Path:
        """Get Slack credentials path."""
        return Path(r"C:\claude\json\slack_credentials.json")

    @property
    def slack_token_path(self) -> Path:
        """Get Slack token path."""
        return Path(r"C:\claude\json\slack_token.json")

    @property
    def claude_sessions_path(self) -> Path:
        """Get Claude Code sessions directory."""
        return Path.home() / ".claude" / "projects"

    def __repr__(self) -> str:
        return f"Config(path={self._config_path})"
