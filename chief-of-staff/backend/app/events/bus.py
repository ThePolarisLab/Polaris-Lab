"""Thread-safe in-process publish/subscribe infrastructure."""

from collections import deque
from collections.abc import Callable
from copy import deepcopy
from threading import RLock

from app.events.models import ConnectorEvent, EventBusMetrics

EventHandler = Callable[[ConnectorEvent], None]


class EventBus:
    """Dispatch events synchronously while isolating subscriber failures."""

    def __init__(self, history_size: int = 100) -> None:
        if history_size < 1:
            raise ValueError("history_size must be at least 1")
        self._history: deque[ConnectorEvent] = deque(maxlen=history_size)
        self._subscribers: dict[str, EventHandler] = {}
        self._lock = RLock()
        self._metrics = EventBusMetrics()

    def subscribe(self, name: str, handler: EventHandler) -> None:
        """Register one uniquely named subscriber."""
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("subscriber name cannot be empty")
        with self._lock:
            if normalized in self._subscribers:
                raise ValueError(f"subscriber already registered: {name}")
            self._subscribers[normalized] = handler

    def unsubscribe(self, name: str) -> bool:
        """Remove a subscriber and return whether it existed."""
        with self._lock:
            return self._subscribers.pop(name.strip().lower(), None) is not None

    def publish(self, event: ConnectorEvent) -> list[str]:
        """Publish an event and return subscriber names that failed delivery."""
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers.items())
            self._metrics.events_published += 1
            self._metrics.last_published_at = event.occurred_at

        failures: list[str] = []
        for name, handler in subscribers:
            with self._lock:
                self._metrics.deliveries_attempted += 1
            try:
                handler(event.model_copy(deep=True))
            except Exception:
                failures.append(name)
                with self._lock:
                    self._metrics.deliveries_failed += 1
            else:
                with self._lock:
                    self._metrics.deliveries_succeeded += 1
        return failures

    def recent(self, limit: int = 20) -> list[ConnectorEvent]:
        """Return newest events first without exposing mutable internal state."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._lock:
            events = list(self._history)[-limit:]
        return [event.model_copy(deep=True) for event in reversed(events)]

    def metrics(self) -> EventBusMetrics:
        """Return a snapshot of current event bus metrics."""
        with self._lock:
            snapshot = deepcopy(self._metrics)
            snapshot.subscriber_count = len(self._subscribers)
            snapshot.retained_events = len(self._history)
        return snapshot


event_bus = EventBus()
