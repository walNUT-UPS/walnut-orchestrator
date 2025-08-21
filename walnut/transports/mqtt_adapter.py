"""
MQTT Transport Adapter using Paho-MQTT.
"""
import time
import uuid
import json
import logging
import anyio
import threading
import paho.mqtt.client as mqtt
from typing import Dict, Any, Optional, Callable

from .base import TransportAdapter, Subscription

logger = logging.getLogger(__name__)


class MqttSubscription(Subscription):
    """Represents an active MQTT subscription."""
    def __init__(self, client: mqtt.Client, topic: str):
        self._client = client
        self._topic = topic

    def unsubscribe(self) -> None:
        logger.info(f"Unsubscribing from MQTT topic: {self._topic}")
        self._client.unsubscribe(self._topic)
        # In a more complex app, we might disconnect if no subscriptions are left.


class MqttAdapter:
    """
    A transport adapter for MQTT communication using Paho-MQTT.
    - `call` is for request/response or fire-and-forget publish.
    - `subscribe` is for persistent, event-driven subscriptions.
    """
    name: str = "mqtt"

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._client: Optional[mqtt.Client] = None
        self._response_payload: Optional[bytes] = None
        self._response_received = threading.Event()
        self._is_subscription_client = False

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        """Stores MQTT config and can pre-connect for subscriptions."""
        self._config = instance_cfg.get("mqtt", instance_cfg)

    def _create_client(self) -> mqtt.Client:
        """Creates and configures a Paho MQTT client."""
        client_id = f"walnut-mqtt-{uuid.uuid4()}"
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

        username = self._config.get("username")
        password = self._config.get("password")
        if username:
            client.username_pw_set(username, password)

        # Add TLS support here if needed from config

        return client

    # --- `call` method implementation (request/response) ---

    def _on_message_for_call(self, client, userdata, msg):
        """Callback used only for the temporary subscription in a `call`."""
        self._response_payload = msg.payload
        self._response_received.set()

    def _publish_and_wait(self, request: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        """Synchronous helper for request/response `call` operations."""
        client = self._create_client()

        broker = self._config.get("host")
        port = int(self._config.get("port", 1883))

        try:
            client.connect(broker, port, 60)

            publish_topic = request["topic"]
            payload = request.get("payload")
            response_topic = request.get("response_topic")

            if isinstance(payload, dict):
                payload = json.dumps(payload)

            if response_topic:
                self._response_received.clear()
                self._response_payload = None
                client.subscribe(response_topic)
                client.on_message = self._on_message_for_call
                client.loop_start()

            client.publish(publish_topic, payload, qos=int(request.get("qos", 0)))

            if response_topic:
                if not self._response_received.wait(timeout=timeout_s):
                    raise TimeoutError("Timed out waiting for MQTT response.")

                return {"ok": True, "status": 0, "data": self._response_payload, "raw": self._response_payload}
            else:
                return {"ok": True, "status": 0, "data": None, "raw": None}
        finally:
            if client.is_connected():
                client.loop_stop(force=True)
                client.disconnect()

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """Executes a publish or request/response operation over MQTT."""
        op_timeout = timeout_s or float(self._config.get("timeout_s", 10.0))
        start_time = time.monotonic()

        try:
            result = await anyio.to_thread.run_sync(self._publish_and_wait, request, op_timeout)
        except Exception as e:
            result = {
                "ok": False, "status": None,
                "data": {"error": f"MQTT call failed: {e.__class__.__name__}", "message": str(e)}, "raw": str(e)
            }

        latency_ms = int((time.monotonic() - start_time) * 1000)
        result["latency_ms"] = latency_ms
        return result

    # --- `subscribe` method implementation ---

    def subscribe(self, request: Dict[str, Any], on_event: Callable[[Dict[str, Any]], None]) -> "Subscription":
        """Establishes a persistent subscription to an MQTT topic."""
        if not self._client or not self._client.is_connected():
            self._client = self._create_client()
            self._is_subscription_client = True

            def on_message_for_sub(client, userdata, msg):
                """Permanent callback for subscriptions."""
                try:
                    payload_data = json.loads(msg.payload)
                except json.JSONDecodeError:
                    payload_data = msg.payload.decode('utf-8', errors='ignore')

                event = {
                    "topic": msg.topic,
                    "payload": payload_data,
                    "qos": msg.qos,
                    "retain": msg.retain
                }
                on_event(event)

            self._client.on_message = on_message_for_sub
            broker = self._config.get("host")
            port = int(self._config.get("port", 1883))
            self._client.connect(broker, port, 60)
            self._client.loop_start()

        topic = request["topic"]
        qos = int(request.get("qos", 0))
        self._client.subscribe(topic, qos)
        logger.info(f"Established MQTT subscription to: {topic}")

        return MqttSubscription(client=self._client, topic=topic)

    async def close(self) -> None:
        """Closes the MQTT client if it was used for subscriptions."""
        if self._client and self._client.is_connected():
            logger.info("Closing persistent MQTT client.")
            # Use a thread to call blocking paho methods
            await anyio.to_thread.run_sync(self._client.loop_stop, force=True)
            await anyio.to_thread.run_sync(self._client.disconnect)
            self._client = None
