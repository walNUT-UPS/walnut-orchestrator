"""
IPMI Transport Adapter using 'ipmitool' CLI.

Executes IPMI commands via subprocess. Requires 'ipmitool' installed on host.
Supports chassis power ops and sensor listing.
"""
from typing import Dict, Any, Optional, List
import time
import subprocess
import shlex
import anyio

from .base import TransportAdapter


class IpmiAdapter:
    name: str = "ipmi"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        self._config = instance_cfg.get("ipmi", instance_cfg)

    def _run(self, args: List[str], timeout: Optional[float]) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            latency_ms = int((time.monotonic() - start) * 1000)
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "status": proc.returncode,
                "data": proc.stdout if ok else {"error": proc.stderr.strip() or proc.stdout},
                "raw": proc.stdout + ("\n" + proc.stderr if proc.stderr else ""),
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        host = self._config.get("host")
        username = self._config.get("username")
        password = self._config.get("password")
        interface = self._config.get("interface", "lanplus")
        port = self._config.get("port")
        cipher_suite = self._config.get("cipher_suite")
        if not host or not username or password is None:
            raise ValueError("IPMI config requires 'host', 'username', and 'password'.")

        base = ["ipmitool", "-I", interface, "-H", host, "-U", username, "-P", password]
        if port:
            base += ["-p", str(port)]
        if cipher_suite:
            base += ["-C", str(cipher_suite)]

        op = (request.get("op") or "chassis_power").lower()
        if op == "chassis_power":
            action = (request.get("action") or "status").lower()
            args = base + ["chassis", "power", action]
        elif op == "sensor_list":
            args = base + ["sensor", "list"]
        elif op == "raw":
            raw_args = request.get("args")
            if not isinstance(raw_args, list) or not raw_args:
                raise ValueError("IPMI raw op requires list 'args'")
            args = base + ["raw"] + [str(x) for x in raw_args]
        else:
            raise ValueError(f"Unsupported IPMI op: {op}")

        return await anyio.to_thread.run_sync(self._run, args, timeout_s)

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("ipmi transport does not support subscriptions.")

    async def close(self) -> None:
        return None
