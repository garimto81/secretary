"""
Custom exceptions for Secretary.

Exception hierarchy:
    SecretaryError (base)
    ├── ConfigurationError
    ├── AuthenticationError
    ├── AdapterError
    │   └── RateLimitError
    └── ActionError
"""

from __future__ import annotations

from typing import Any


class SecretaryError(Exception):
    """Base exception for all Secretary errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """
        Initialize the exception.

        Args:
            message: Error message
            details: Additional error details (optional)
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message


class ConfigurationError(SecretaryError):
    """
    Raised when configuration is invalid or missing.

    Examples:
        - Missing required config file
        - Invalid YAML syntax
        - Missing required environment variable
    """

    pass


class AuthenticationError(SecretaryError):
    """
    Raised when authentication fails.

    Examples:
        - Invalid API key
        - Expired OAuth token
        - Missing credentials
    """

    def __init__(
        self,
        message: str,
        service: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize authentication error.

        Args:
            message: Error message
            service: Service that failed authentication (e.g., "gmail", "github")
            details: Additional error details
        """
        super().__init__(message, details)
        self.service = service

    def __str__(self) -> str:
        if self.service:
            return f"[{self.service}] {self.message}"
        return self.message


class AdapterError(SecretaryError):
    """
    Raised when an adapter fails to communicate with external service.

    Examples:
        - Network error
        - API error response
        - Timeout
    """

    def __init__(
        self,
        message: str,
        adapter: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize adapter error.

        Args:
            message: Error message
            adapter: Name of the adapter (e.g., "gmail", "slack")
            status_code: HTTP status code if applicable
            details: Additional error details
        """
        super().__init__(message, details)
        self.adapter = adapter
        self.status_code = status_code

    def __str__(self) -> str:
        parts = []
        if self.adapter:
            parts.append(f"[{self.adapter}]")
        if self.status_code:
            parts.append(f"HTTP {self.status_code}:")
        parts.append(self.message)
        return " ".join(parts)


class RateLimitError(AdapterError):
    """
    Raised when rate limit is exceeded.

    Includes retry information when available.
    """

    def __init__(
        self,
        message: str,
        adapter: str | None = None,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize rate limit error.

        Args:
            message: Error message
            adapter: Name of the adapter
            retry_after: Seconds to wait before retry (if provided by API)
            details: Additional error details
        """
        super().__init__(message, adapter=adapter, status_code=429, details=details)
        self.retry_after = retry_after

    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            return f"{base} (retry after {self.retry_after}s)"
        return base


class ActionError(SecretaryError):
    """
    Raised when an action fails to execute.

    Examples:
        - Failed to create calendar event
        - Failed to send notification
        - Failed to generate response
    """

    def __init__(
        self,
        message: str,
        action: str | None = None,
        recoverable: bool = True,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize action error.

        Args:
            message: Error message
            action: Name of the action (e.g., "calendar_create", "toast_notify")
            recoverable: Whether the action can be retried
            details: Additional error details
        """
        super().__init__(message, details)
        self.action = action
        self.recoverable = recoverable

    def __str__(self) -> str:
        parts = []
        if self.action:
            parts.append(f"[{self.action}]")
        parts.append(self.message)
        if not self.recoverable:
            parts.append("(non-recoverable)")
        return " ".join(parts)


class AnalysisError(SecretaryError):
    """
    Raised when analysis fails.

    Examples:
        - Failed to parse notification
        - LLM API error during classification
        - Invalid input data
    """

    def __init__(
        self,
        message: str,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize analysis error.

        Args:
            message: Error message
            source: Source of data that failed analysis (e.g., "email", "slack")
            details: Additional error details
        """
        super().__init__(message, details)
        self.source = source

    def __str__(self) -> str:
        if self.source:
            return f"Analysis failed for {self.source}: {self.message}"
        return f"Analysis failed: {self.message}"
