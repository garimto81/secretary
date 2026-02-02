"""
Secretary - AI-powered notification analysis and automation.

A unified system for analyzing Gmail, Calendar, GitHub, Slack, and LLM sessions
to generate daily reports and execute automation actions.
"""

__version__ = "2.0.0"

from secretary.core.config import Config
from secretary.core.events import EventBus
from secretary.core.exceptions import (
    AdapterError,
    AuthenticationError,
    ConfigurationError,
    RateLimitError,
    SecretaryError,
)
from secretary.cli.main import cli

__all__ = [
    "__version__",
    "Config",
    "EventBus",
    "SecretaryError",
    "AuthenticationError",
    "AdapterError",
    "RateLimitError",
    "ConfigurationError",
    "cli",
]
