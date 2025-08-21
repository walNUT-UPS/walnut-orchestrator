"""
Base interfaces for transport adapters.
"""
from typing import Protocol, Callable, Any, Dict, Optional

class Subscription(Protocol):
    """
    Protocol for a subscription to an event stream.
    """
    def unsubscribe(self) -> None:
        """
        Cancels the subscription.
        """
        ...

class TransportAdapter(Protocol):
    """
    Protocol for a transport adapter.

    A transport adapter provides a standardized interface for interacting with
    different communication protocols (e.g., HTTP, SSH, MQTT).
    """
    name: str

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        """
        Prepares the adapter for use with a specific integration instance.

        This method is called once before any other methods. It should be used
        to configure the adapter with the connection details from the instance
        configuration.

        Args:
            instance_cfg: The configuration for the integration instance.
        """
        ...

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes a request-response operation.

        Args:
            request: The request payload, specific to the transport.
            timeout_s: An optional timeout in seconds for the operation.

        Returns:
            A dictionary with the normalized result:
            {
                "ok": bool,
                "status": int | None,
                "data": Any,
                "raw": Any,
                "latency_ms": int
            }
        """
        ...

    def subscribe(self, request: Dict[str, Any], on_event: Callable[[Dict[str, Any]], None]) -> "Subscription":
        """
        Subscribes to an event stream.

        This method is optional and should raise NotImplementedError if the
        transport does not support subscriptions.

        Args:
            request: The subscription request payload.
            on_event: A callback function to be called with each event.

        Returns:
            A Subscription object that can be used to cancel the subscription.
        """
        raise NotImplementedError(f"{self.name} transport does not support subscriptions.")

    async def close(self) -> None:
        """
        Closes the transport and releases any resources.
        """
        ...
