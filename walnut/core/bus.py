"""
A simple, in-memory, async-friendly Event Bus.

This provides a lightweight pub/sub mechanism for decoupling different parts
of the application.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Dict, List, Any, Awaitable

logger = logging.getLogger(__name__)

# Type hint for an async callback that takes one argument
EventCallback = Callable[[Any], Awaitable[None]]

class EventBus:
    """
    A simple asynchronous event bus for pub/sub interactions.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[EventCallback]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, callback: EventCallback):
        """
        Subscribes a callback to a specific topic.

        Args:
            topic: The topic to subscribe to (e.g., "mqtt/devices/+/status").
            callback: An async function to be called when an event is published.
        """
        async with self._lock:
            logger.debug(f"New subscription to topic: {topic}")
            self._subscribers[topic].append(callback)

    async def publish(self, topic: str, data: Any):
        """
        Publishes an event to all subscribers of a topic.

        Args:
            topic: The topic to publish the event to.
            data: The data payload of the event.
        """
        if topic in self._subscribers:
            logger.debug(f"Publishing event to topic '{topic}' for {len(self._subscribers[topic])} subscribers.")
            # Create tasks for all callbacks to run concurrently
            tasks = [
                asyncio.create_task(callback(data))
                for callback in self._subscribers[topic]
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

# Global instance of the EventBus
_event_bus_instance: EventBus | None = None

def get_event_bus() -> EventBus:
    """
    Returns the singleton instance of the EventBus.
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance
