"""
Pub/Sub event bus for loose coupling between components.

Supports both synchronous and asynchronous event handlers.
Events are typed by string identifiers with Any data payload.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type aliases
SyncHandler = Callable[[Any], None]
AsyncHandler = Callable[[Any], Any]  # Coroutine
Handler = SyncHandler | AsyncHandler


class EventBus:
    """
    Pub/Sub event bus for component communication.

    Usage:
        bus = EventBus()

        # Subscribe to events
        def on_email_received(data):
            print(f"New email: {data['subject']}")

        bus.subscribe("email.received", on_email_received)

        # Publish events
        bus.publish("email.received", {"subject": "Hello"})

        # Async support
        async def on_notification(data):
            await process_notification(data)

        bus.subscribe("notification.new", on_notification)
        await bus.publish_async("notification.new", data)
    """

    def __init__(self):
        """Initialize the event bus."""
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._async_handlers: dict[str, list[AsyncHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        """
        Subscribe a handler to an event type.

        Args:
            event_type: Event type identifier (e.g., "email.received")
            handler: Callback function (sync or async)

        Returns:
            Unsubscribe function
        """
        if asyncio.iscoroutinefunction(handler):
            self._async_handlers[event_type].append(handler)
            logger.debug("Async handler subscribed to: %s", event_type)

            def unsubscribe():
                self._async_handlers[event_type].remove(handler)
                logger.debug("Async handler unsubscribed from: %s", event_type)

        else:
            self._handlers[event_type].append(handler)
            logger.debug("Sync handler subscribed to: %s", event_type)

            def unsubscribe():
                self._handlers[event_type].remove(handler)
                logger.debug("Sync handler unsubscribed from: %s", event_type)

        return unsubscribe

    def unsubscribe(self, event_type: str, handler: Handler) -> bool:
        """
        Unsubscribe a handler from an event type.

        Args:
            event_type: Event type identifier
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        if asyncio.iscoroutinefunction(handler):
            try:
                self._async_handlers[event_type].remove(handler)
                logger.debug("Async handler unsubscribed from: %s", event_type)
                return True
            except ValueError:
                return False
        else:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug("Sync handler unsubscribed from: %s", event_type)
                return True
            except ValueError:
                return False

    def publish(self, event_type: str, data: Any = None) -> int:
        """
        Publish an event to all subscribed sync handlers.

        Note: Async handlers are NOT called. Use publish_async for those.

        Args:
            event_type: Event type identifier
            data: Event data payload

        Returns:
            Number of handlers called
        """
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug("No sync handlers for event: %s", event_type)
            return 0

        logger.debug("Publishing %s to %d sync handlers", event_type, len(handlers))

        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(
                    "Error in handler for %s: %s",
                    event_type,
                    e,
                    exc_info=True,
                )

        return len(handlers)

    async def publish_async(self, event_type: str, data: Any = None) -> int:
        """
        Publish an event to all subscribed handlers (sync and async).

        Args:
            event_type: Event type identifier
            data: Event data payload

        Returns:
            Number of handlers called
        """
        sync_handlers = self._handlers.get(event_type, [])
        async_handlers = self._async_handlers.get(event_type, [])

        total = len(sync_handlers) + len(async_handlers)

        if total == 0:
            logger.debug("No handlers for event: %s", event_type)
            return 0

        logger.debug(
            "Publishing %s to %d sync + %d async handlers",
            event_type,
            len(sync_handlers),
            len(async_handlers),
        )

        # Call sync handlers
        for handler in sync_handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(
                    "Error in sync handler for %s: %s",
                    event_type,
                    e,
                    exc_info=True,
                )

        # Call async handlers concurrently
        if async_handlers:
            tasks = []
            for handler in async_handlers:
                tasks.append(asyncio.create_task(self._safe_async_call(handler, event_type, data)))
            await asyncio.gather(*tasks, return_exceptions=True)

        return total

    async def _safe_async_call(
        self,
        handler: AsyncHandler,
        event_type: str,
        data: Any,
    ) -> None:
        """Safely call an async handler with error handling."""
        try:
            await handler(data)
        except Exception as e:
            logger.error(
                "Error in async handler for %s: %s",
                event_type,
                e,
                exc_info=True,
            )

    def clear(self, event_type: str | None = None) -> None:
        """
        Clear all handlers for an event type, or all handlers if None.

        Args:
            event_type: Event type to clear, or None for all
        """
        if event_type:
            self._handlers.pop(event_type, None)
            self._async_handlers.pop(event_type, None)
            logger.debug("Cleared handlers for: %s", event_type)
        else:
            self._handlers.clear()
            self._async_handlers.clear()
            logger.debug("Cleared all event handlers")

    def get_handlers(self, event_type: str) -> list[Handler]:
        """Get all handlers for an event type."""
        return list(self._handlers.get(event_type, [])) + list(
            self._async_handlers.get(event_type, [])
        )

    @property
    def event_types(self) -> set[str]:
        """Get all registered event types."""
        return set(self._handlers.keys()) | set(self._async_handlers.keys())

    def __repr__(self) -> str:
        total_sync = sum(len(h) for h in self._handlers.values())
        total_async = sum(len(h) for h in self._async_handlers.values())
        return f"EventBus(sync={total_sync}, async={total_async})"


# Predefined event types for type safety
class EventTypes:
    """Standard event type constants."""

    # Notification events
    NOTIFICATION_RECEIVED = "notification.received"
    NOTIFICATION_ANALYZED = "notification.analyzed"
    NOTIFICATION_PROCESSED = "notification.processed"

    # Email events
    EMAIL_RECEIVED = "email.received"
    EMAIL_ANALYZED = "email.analyzed"
    EMAIL_ACTION_REQUIRED = "email.action_required"

    # Calendar events
    CALENDAR_EVENT_UPCOMING = "calendar.event_upcoming"
    CALENDAR_CONFLICT_DETECTED = "calendar.conflict_detected"

    # GitHub events
    GITHUB_PR_REVIEW_NEEDED = "github.pr_review_needed"
    GITHUB_ISSUE_ASSIGNED = "github.issue_assigned"

    # Slack events
    SLACK_MENTION_RECEIVED = "slack.mention_received"
    SLACK_URGENT_MESSAGE = "slack.urgent_message"

    # Action events
    ACTION_TRIGGERED = "action.triggered"
    ACTION_COMPLETED = "action.completed"
    ACTION_FAILED = "action.failed"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
