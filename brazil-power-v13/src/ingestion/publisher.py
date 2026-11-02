"""Event publisher abstraction for In-Process and Cloud Pub/Sub dispatch."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol


class EventPublisher(Protocol):
    """Protocol for publishing ingestion and audit events."""

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """Publish a message to the given topic and return a message ID."""
        ...


class InProcessEventPublisher:
    """Deterministic in-process publisher for local/unit/integration execution."""

    def __init__(self) -> None:
        self.published_messages: list[tuple[str, dict[str, Any]]] = []
        self._subscribers: dict[
            str, list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]]
        ] = {}

    def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self._subscribers.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        msg_id = f"inproc-{len(self.published_messages) + 1:06d}"
        self.published_messages.append((topic, payload))
        for handler in self._subscribers.get(topic, []):
            await handler(payload)
        return msg_id
