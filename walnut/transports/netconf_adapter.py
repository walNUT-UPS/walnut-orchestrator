"""
NETCONF Transport Adapter using ncclient.

Supports basic get, get-config, and edit-config operations.
"""
from typing import Dict, Any, Optional
import time
import anyio

from .base import TransportAdapter


class NetconfAdapter:
    name: str = "netconf"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        self._config = instance_cfg.get("netconf", instance_cfg)

    def _call(self, request: Dict[str, Any], timeout_s: Optional[float]) -> Dict[str, Any]:
        try:
            from ncclient import manager
        except Exception as e:
            raise RuntimeError("ncclient is required for NETCONF operations. Install 'ncclient'.") from e

        host = self._config.get("host")
        port = int(self._config.get("port", 830))
        username = self._config.get("username")
        password = self._config.get("password")
        hostkey_verify = bool(self._config.get("hostkey_verify", False))
        allow_agent = bool(self._config.get("allow_agent", False))
        look_for_keys = bool(self._config.get("look_for_keys", False))
        if not host or not username or password is None:
            raise ValueError("NETCONF requires 'host', 'username', and 'password' in config.")

        op = (request.get("op") or "get").lower()
        start = time.monotonic()
        try:
            with manager.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                hostkey_verify=hostkey_verify,
                allow_agent=allow_agent,
                look_for_keys=look_for_keys,
                timeout=timeout_s or float(self._config.get("timeout_s", 10.0)),
            ) as m:
                if op == "get":
                    filter_xml = request.get("filter")  # string or dict
                    if filter_xml is not None:
                        reply = m.get(filter=filter_xml)
                    else:
                        reply = m.get()
                    data = reply.data_xml
                elif op == "get_config":
                    source = request.get("source", "running")
                    filter_xml = request.get("filter")
                    reply = m.get_config(source=source, filter=filter_xml)
                    data = reply.data_xml
                elif op == "edit_config":
                    target = request.get("target", "running")
                    config_xml = request.get("config")
                    if not config_xml:
                        raise ValueError("edit_config requires 'config'")
                    reply = m.edit_config(target=target, config=config_xml)
                    data = reply.xml
                else:
                    raise ValueError(f"Unsupported NETCONF op: {op}")
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "status": 0, "data": data, "raw": data, "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self._call, request, timeout_s)

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("netconf transport subscribe not implemented in this adapter.")

    async def close(self) -> None:
        return None

