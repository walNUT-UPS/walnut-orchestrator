"""
Transport Adapter Registry.

This module provides a central registry for discovering and accessing transport
adapters. Adapters are classes that conform to the TransportAdapter protocol
and provide a standardized way to interact with different communication protocols.
"""
import logging
from typing import Dict, Type, Any, Callable

from .base import TransportAdapter, Subscription

logger = logging.getLogger(__name__)

REGISTRY: Dict[str, Type[TransportAdapter]] = {}


def register(name: str, cls: Type[TransportAdapter]):
    """
    Registers a transport adapter class.
    """
    if name in REGISTRY:
        logger.warning(f"Transport adapter '{name}' is being overridden.")
    REGISTRY[name] = cls
    logger.info(f"Registered transport adapter: {name}")


def get(name: str) -> TransportAdapter:
    """
    Retrieves an unconfigured instance of a transport adapter.
    """
    adapter_class = REGISTRY.get(name)
    if not adapter_class:
        # For backward compatibility, default to 'http' if not specified.
        # This is a transitional assumption.
        if name is None or name == "":
            logger.warning("Transport not specified, defaulting to 'http' for backward compatibility.")
            adapter_class = REGISTRY.get("http")
            if not adapter_class:
                 raise ValueError("Default transport 'http' is not registered.")
        else:
            raise ValueError(f"Unknown transport: {name}")
    return adapter_class()


def _create_stub_adapter(adapter_name: str) -> Type[TransportAdapter]:
    """
    A factory to create stub adapter classes for transports that are not yet implemented.
    """

    class StubAdapter:
        name: str = adapter_name

        def prepare(self, instance_cfg: Dict[str, Any]) -> None:
            raise NotImplementedError(f"Transport '{self.name}' is a stub and not implemented.")

        def call(self, request: Dict[str, Any], *, timeout_s: float | None = None) -> Dict[str, Any]:
            raise NotImplementedError(f"Transport '{self.name}' is a stub and not implemented.")

        def subscribe(self, request: Dict[str, Any], on_event: Callable[[Dict[str, Any]], None]) -> "Subscription":
            raise NotImplementedError(f"Transport '{self.name}' is a stub and not implemented.")

        def close(self) -> None:
            pass

    # Manually annotate that the class conforms to the protocol
    conforming_stub: Type[TransportAdapter] = StubAdapter
    return conforming_stub


def init_transports():
    """
    Initializes and registers all built-in transport adapters.
    This function should be called at application startup.
    """
    logger.info("Initializing transport adapters...")

    # Register real adapters
    from .http_adapter import HttpAdapter
    register("http", HttpAdapter)
    from .ssh_adapter import SshAdapter
    register("ssh", SshAdapter)
    from .mqtt_adapter import MqttAdapter
    register("mqtt", MqttAdapter)
    from .websocket_adapter import WebsocketAdapter
    register("websocket", WebsocketAdapter)
    # Newly implemented adapters
    try:
        from .telnet_adapter import TelnetAdapter
        register("telnet", TelnetAdapter)
    except Exception as e:
        logger.warning("Telnet adapter unavailable: %s", e)
    try:
        from .redfish_adapter import RedfishAdapter
        register("redfish", RedfishAdapter)
    except Exception as e:
        logger.warning("Redfish adapter unavailable: %s", e)
    try:
        from .snmp_adapter import SnmpAdapter
        register("snmp", SnmpAdapter)
    except Exception as e:
        logger.warning("SNMP adapter unavailable: %s", e)
    try:
        from .modbus_adapter import ModbusAdapter
        register("modbus", ModbusAdapter)
    except Exception as e:
        logger.warning("Modbus adapter unavailable: %s", e)
    try:
        from .ipmi_adapter import IpmiAdapter
        register("ipmi", IpmiAdapter)
    except Exception as e:
        logger.warning("IPMI adapter unavailable: %s", e)
    try:
        from .gnmi_adapter import GnmiAdapter
        register("gnmi", GnmiAdapter)
    except Exception as e:
        logger.warning("gNMI adapter unavailable: %s", e)
    try:
        from .netconf_adapter import NetconfAdapter
        register("netconf", NetconfAdapter)
    except Exception as e:
        logger.warning("NETCONF adapter unavailable: %s", e)

    # Keep placeholder stubs for any future protocols (none at the moment)

    logger.info(f"Transport adapters initialized. Registered: {list(REGISTRY.keys())}")
