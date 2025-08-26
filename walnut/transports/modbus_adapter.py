"""
Modbus Transport Adapter using pymodbus.

Supports Modbus/TCP read and write operations. Uses async client when
available; otherwise runs sync client in a thread.
"""
from typing import Dict, Any, Optional
import time
import anyio

from .base import TransportAdapter


class ModbusAdapter:
    name: str = "modbus"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self._mode: str = "async"  # or "sync"

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        self._config = instance_cfg.get("modbus", instance_cfg)
        # Try to import async client
        try:
            from pymodbus.client import AsyncModbusTcpClient  # noqa: F401
            self._mode = "async"
        except Exception:
            self._mode = "sync"

    async def _call_async(self, request: Dict[str, Any], timeout_s: Optional[float]) -> Dict[str, Any]:
        from pymodbus.client import AsyncModbusTcpClient
        host = self._config.get("host")
        port = int(self._config.get("port", 502))
        unit = int(request.get("unit", self._config.get("unit", 1)))
        if not host:
            raise ValueError("Modbus 'host' is required in config.")

        client = AsyncModbusTcpClient(host=host, port=port, timeout=timeout_s or float(self._config.get("timeout_s", 5.0)))
        start = time.monotonic()
        try:
            await client.connect()
            op = (request.get("op") or "read_holding_registers").lower()
            address = int(request.get("address", 0))
            count = int(request.get("count", 1))
            if op == "read_holding_registers":
                rr = await client.read_holding_registers(address, count, slave=unit)
                data = list(rr.registers) if hasattr(rr, 'registers') else None
            elif op == "read_input_registers":
                rr = await client.read_input_registers(address, count, slave=unit)
                data = list(rr.registers) if hasattr(rr, 'registers') else None
            elif op == "read_coils":
                rr = await client.read_coils(address, count, slave=unit)
                data = list(rr.bits) if hasattr(rr, 'bits') else None
            elif op == "read_discrete_inputs":
                rr = await client.read_discrete_inputs(address, count, slave=unit)
                data = list(rr.bits) if hasattr(rr, 'bits') else None
            elif op == "write_coil":
                value = bool(request.get("value", True))
                rr = await client.write_coil(address, value, slave=unit)
                data = {"written": bool(getattr(rr, 'value', True))}
            elif op == "write_register":
                value = int(request.get("value"))
                rr = await client.write_register(address, value, slave=unit)
                data = {"written": True}
            else:
                raise ValueError(f"Unsupported Modbus op: {op}")

            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "status": 0, "data": {"result": data}, "raw": data, "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}
        finally:
            try:
                await client.close()
            except Exception:
                pass

    def _call_sync(self, request: Dict[str, Any], timeout_s: Optional[float]) -> Dict[str, Any]:
        from pymodbus.client import ModbusTcpClient
        host = self._config.get("host")
        port = int(self._config.get("port", 502))
        unit = int(request.get("unit", self._config.get("unit", 1)))
        if not host:
            raise ValueError("Modbus 'host' is required in config.")

        client = ModbusTcpClient(host=host, port=port, timeout=timeout_s or float(self._config.get("timeout_s", 5.0)))
        start = time.monotonic()
        try:
            client.connect()
            op = (request.get("op") or "read_holding_registers").lower()
            address = int(request.get("address", 0))
            count = int(request.get("count", 1))
            if op == "read_holding_registers":
                rr = client.read_holding_registers(address, count, unit=unit)
                data = list(rr.registers) if hasattr(rr, 'registers') else None
            elif op == "read_input_registers":
                rr = client.read_input_registers(address, count, unit=unit)
                data = list(rr.registers) if hasattr(rr, 'registers') else None
            elif op == "read_coils":
                rr = client.read_coils(address, count, unit=unit)
                data = list(rr.bits) if hasattr(rr, 'bits') else None
            elif op == "read_discrete_inputs":
                rr = client.read_discrete_inputs(address, count, unit=unit)
                data = list(rr.bits) if hasattr(rr, 'bits') else None
            elif op == "write_coil":
                value = bool(request.get("value", True))
                rr = client.write_coil(address, value, unit=unit)
                data = {"written": True}
            elif op == "write_register":
                value = int(request.get("value"))
                rr = client.write_register(address, value, unit=unit)
                data = {"written": True}
            else:
                raise ValueError(f"Unsupported Modbus op: {op}")

            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "status": 0, "data": {"result": data}, "raw": data, "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}
        finally:
            try:
                client.close()
            except Exception:
                pass

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        if self._mode == "async":
            return await self._call_async(request, timeout_s)
        return await anyio.to_thread.run_sync(self._call_sync, request, timeout_s)

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("modbus transport does not support subscriptions.")

    async def close(self) -> None:
        return None
