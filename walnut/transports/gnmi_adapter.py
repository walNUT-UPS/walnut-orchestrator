"""
gNMI Transport Adapter using pygnmi.

Supports basic Get operation. Requires 'pygnmi' package and device with gNMI.
"""
from typing import Dict, Any, Optional, List, Tuple
import time
import anyio

from .base import TransportAdapter


class GnmiAdapter:
    name: str = "gnmi"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        self._config = instance_cfg.get("gnmi", instance_cfg)

    def _get(self, target: Tuple[str, int], username: Optional[str], password: Optional[str], insecure: bool, paths: List[str], encoding: Optional[str], timeout: Optional[float]) -> Dict[str, Any]:
        try:
            from pygnmi.client import gNMIclient
        except Exception as e:
            raise RuntimeError("pygnmi is required for gNMI operations. Install 'pygnmi'.") from e

        start = time.monotonic()
        try:
            with gNMIclient(target=target, username=username, password=password, insecure=insecure, timeout=timeout) as c:
                result = c.get(path=paths, encoding=encoding or "JSON_IETF")
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "status": 0, "data": result, "raw": result, "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        host = self._config.get("host")
        port = int(self._config.get("port", 57400))
        username = self._config.get("username")
        password = self._config.get("password")
        insecure = bool(self._config.get("insecure", True))

        if not host:
            raise ValueError("gNMI 'host' is required in config.")

        op = (request.get("op") or "get").lower()
        if op == "get":
            paths = request.get("paths") or request.get("path")
            if isinstance(paths, str):
                paths = [paths]
            if not isinstance(paths, list) or not paths:
                raise ValueError("gNMI get requires 'paths' (list or string)")
            encoding = request.get("encoding")
            return await anyio.to_thread.run_sync(self._get, (host, port), username, password, insecure, paths, encoding, timeout_s)
        else:
            raise ValueError(f"Unsupported gNMI op: {op}")

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("gnmi transport subscribe not implemented in this adapter.")

    async def close(self) -> None:
        return None

