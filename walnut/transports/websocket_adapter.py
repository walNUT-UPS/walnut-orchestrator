"""
WebSocket Transport Adapter using the 'websockets' library.
"""
import time
import json
import asyncio
import logging
import websockets
from typing import Dict, Any, Optional, Callable

from .base import TransportAdapter, Subscription

logger = logging.getLogger(__name__)


class WebSocketSubscription(Subscription):
    """Represents an active WebSocket subscription."""
    def __init__(self, connection: websockets.WebSocketClientProtocol, listener_task: asyncio.Task):
        self._connection = connection
        self._listener_task = listener_task

    def unsubscribe(self) -> None:
        logger.info("Cancelling WebSocket listener task and closing connection.")
        self._listener_task.cancel()
        # The connection will be closed by the `_listen` task's finally block.


class WebsocketAdapter:
    """
    A transport adapter for WebSocket communication.
    - `call` is for short-lived request/response interactions.
    - `subscribe` creates a persistent connection for event streams.
    """
    name: str = "websocket"

    def __init__(self):
        self._config: Dict[str, Any] = {}
        # This connection is managed by the `subscribe` method for persistence.
        self._persistent_conn: Optional[websockets.WebSocketClientProtocol] = None
        self._listener_task: Optional[asyncio.Task] = None

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        """Stores WebSocket config."""
        self._config = instance_cfg.get("websocket", instance_cfg)

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """Connects, sends a message, awaits a specific response, and closes."""
        url = request.get("url")
        if not url:
            raise ValueError("WebSocket 'url' is required in the request.")

        send_data = request.get("send")
        expect = request.get("expect", {})
        op_timeout = timeout_s or float(self._config.get("timeout_s", 10.0))

        start_time = time.monotonic()
        try:
            async with websockets.connect(url, open_timeout=op_timeout) as ws:
                if send_data:
                    if isinstance(send_data, dict):
                        send_data = json.dumps(send_data)
                    await ws.send(send_data)

                # Wait for a response that matches the 'expect' condition
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=op_timeout)
                    latency_ms = int((time.monotonic() - start_time) * 1000)

                    match = False
                    if "contains" in expect and expect["contains"] in str(message):
                        match = True
                    # TODO: Implement JSONPath matching for more complex assertions
                    elif not expect: # If no expect rule, any message is a success
                        match = True

                    if match:
                        return {"ok": True, "status": 0, "data": message, "raw": message, "latency_ms": latency_ms}

        except (asyncio.TimeoutError, websockets.exceptions.TimeoutError):
             latency_ms = int((time.monotonic() - start_time) * 1000)
             return {"ok": False, "status": None, "data": {"error": "Timeout", "message": "Timed out waiting for expected message"}, "raw": "", "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            return {"ok": False, "status": None, "data": {"error": f"WebSocket call failed: {e.__class__.__name__}", "message": str(e)}, "raw": str(e), "latency_ms": latency_ms}

    async def _listen(self, ws: websockets.WebSocketClientProtocol, on_event: Callable[[Dict[str, Any]], None]):
        """The background task that listens for messages on a persistent connection."""
        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    data = message
                on_event({"data": data, "raw": message})
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed.")
        except asyncio.CancelledError:
            logger.info("WebSocket listener task cancelled.")
        finally:
            if ws.open:
                await ws.close()

    def subscribe(self, request: Dict[str, Any], on_event: Callable[[Dict[str, Any]], None]) -> "Subscription":
        """Establishes a persistent WebSocket connection for streaming events."""
        if self._listener_task and not self._listener_task.done():
            raise RuntimeError("An active WebSocket subscription already exists for this adapter instance.")

        url = request.get("url")
        if not url:
            raise ValueError("WebSocket 'url' for subscription is required.")

        async def _connect_and_listen():
            try:
                # The connection is established here and passed to the listener
                self._persistent_conn = await websockets.connect(url)
                self._listener_task = asyncio.create_task(self._listen(self._persistent_conn, on_event))
            except Exception as e:
                logger.error(f"Failed to establish WebSocket subscription to {url}: {e}")

        # We need to run the connection logic in the current event loop.
        # This is a bit tricky, as `subscribe` itself is not async.
        # A better design might involve an async `start_subscription` method.
        # For now, we can create a task.
        asyncio.create_task(_connect_and_listen())

        # This is not ideal, as the subscription object is returned before the connection is established.
        # The caller would need to handle potential connection errors asynchronously.
        # However, it fits the synchronous `subscribe` signature.
        return WebSocketSubscription(self._persistent_conn, self._listener_task)

    async def close(self) -> None:
        """Closes the persistent WebSocket connection if it exists."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass # Expected

        if self._persistent_conn and self._persistent_conn.open:
            await self._persistent_conn.close()

        self._listener_task = None
        self._persistent_conn = None
