"""
SNMP Transport Adapter using pysnmp.

Supports SNMP v2c and basic v3 auth/priv. Operations: get, walk, set.
Uses blocking pysnmp hlapi under a worker thread to avoid blocking the loop.
"""
from typing import Dict, Any, Optional, List
import time
import anyio

from .base import TransportAdapter


class SnmpAdapter:
    name: str = "snmp"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        # Support nested block or top-level
        self._config = instance_cfg.get("snmp", instance_cfg)

    def _make_auth(self):
        # Import inside to make dependency optional until used
        try:
            from pysnmp.hlapi import CommunityData, UsmUserData, usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol, usmNoAuthProtocol, usmDESPrivProtocol, usm3DESEDEPrivProtocol, usmAesCfb128Protocol, usmNoPrivProtocol
        except Exception as e:  # pragma: no cover
            raise RuntimeError("pysnmp is required for SNMP operations. Install 'pysnmp'.") from e

        version = str(self._config.get("version", "2c")).lower()
        if version in ("2", "2c"):
            community = self._config.get("community") or self._config.get("community_string") or "public"
            return CommunityData(community, mpModel=1)
        elif version in ("3", "v3"):
            user = self._config.get("user") or self._config.get("username")
            if not user:
                raise ValueError("SNMP v3 requires 'user'/'username'.")
            auth_key = self._config.get("auth_key") or self._config.get("authKey")
            priv_key = self._config.get("priv_key") or self._config.get("privKey")
            auth_proto = (self._config.get("auth_protocol") or "none").lower()
            priv_proto = (self._config.get("priv_protocol") or "none").lower()
            auth_map = {
                "md5": usmHMACMD5AuthProtocol,
                "sha": usmHMACSHAAuthProtocol,
                "none": usmNoAuthProtocol,
            }
            priv_map = {
                "des": usmDESPrivProtocol,
                "3des": usm3DESEDEPrivProtocol,
                "aes": usmAesCfb128Protocol,
                "none": usmNoPrivProtocol,
            }
            return UsmUserData(
                user,
                authKey=auth_key,
                privKey=priv_key,
                authProtocol=auth_map.get(auth_proto, usmNoAuthProtocol),
                privProtocol=priv_map.get(priv_proto, usmNoPrivProtocol),
            )
        else:
            raise ValueError(f"Unsupported SNMP version: {version}")

    def _run(self, request: Dict[str, Any], timeout_s: Optional[float]) -> Dict[str, Any]:
        from pysnmp.hlapi import SnmpEngine, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd, setCmd
        host = self._config.get("host")
        port = int(self._config.get("port", 161))
        if not host:
            raise ValueError("SNMP 'host' is required in config.")
        auth = self._make_auth()
        timeout = float(timeout_s or self._config.get("timeout_s", 5.0))
        retries = int(self._config.get("retries", 1))

        op = (request.get("op") or "get").lower()
        oids = request.get("oids") or request.get("oid")
        if isinstance(oids, str):
            oids = [oids]
        if not isinstance(oids, list) or not oids:
            raise ValueError("SNMP request requires 'oid' or 'oids' list.")
        var_binds = [ObjectType(ObjectIdentity(oid)) for oid in oids]

        engine = SnmpEngine()
        target = UdpTransportTarget((host, port), timeout=timeout, retries=retries)
        ctx = ContextData()

        start = time.monotonic()
        try:
            if op == "get":
                errorIndication, errorStatus, errorIndex, varBinds = next(
                    getCmd(engine, auth, target, ctx, *var_binds)
                )
                data = {}
                if errorIndication:
                    ok = False
                    msg = str(errorIndication)
                elif errorStatus:
                    ok = False
                    msg = f"{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex)-1][0] or '?'}"
                else:
                    ok = True
                    for name, val in varBinds:
                        data[str(name)] = str(val)
                    msg = "ok"
                latency_ms = int((time.monotonic() - start) * 1000)
                return {"ok": ok, "status": 0 if ok else None, "data": data if ok else {"error": msg}, "raw": data if ok else msg, "latency_ms": latency_ms}

            elif op == "walk":
                walk_oid = var_binds[0].__getitem__(0)
                results: Dict[str, str] = {}
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    engine, auth, target, ctx, ObjectType(ObjectIdentity(str(walk_oid))), lexicographicMode=False
                ):
                    if errorIndication:
                        latency_ms = int((time.monotonic() - start) * 1000)
                        return {"ok": False, "status": None, "data": {"error": str(errorIndication)}, "raw": str(errorIndication), "latency_ms": latency_ms}
                    elif errorStatus:
                        latency_ms = int((time.monotonic() - start) * 1000)
                        msg = f"{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex)-1][0] or '?'}"
                        return {"ok": False, "status": None, "data": {"error": msg}, "raw": msg, "latency_ms": latency_ms}
                    else:
                        for name, val in varBinds:
                            results[str(name)] = str(val)
                latency_ms = int((time.monotonic() - start) * 1000)
                return {"ok": True, "status": 0, "data": results, "raw": results, "latency_ms": latency_ms}

            elif op == "set":
                # request should pass pairs: {oids: [{oid: '1.3', type: 'Integer', value: 1}, ...]}
                bindings: List[ObjectType] = []
                from pysnmp.hlapi import Integer, OctetString
                for item in request.get("oids", []):
                    oid = item.get("oid")
                    typ = (item.get("type") or "OctetString").lower()
                    val = item.get("value")
                    if typ in ("int", "integer"):
                        bindings.append(ObjectType(ObjectIdentity(oid), Integer(int(val))))
                    else:
                        bindings.append(ObjectType(ObjectIdentity(oid), OctetString(str(val))))
                if not bindings:
                    raise ValueError("SNMP set requires 'oids' with oid/type/value entries")
                errorIndication, errorStatus, errorIndex, varBinds = next(
                    setCmd(engine, auth, target, ctx, *bindings)
                )
                data = {}
                if errorIndication:
                    ok = False
                    msg = str(errorIndication)
                elif errorStatus:
                    ok = False
                    msg = f"{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex)-1][0] or '?'}"
                else:
                    ok = True
                    for name, val in varBinds:
                        data[str(name)] = str(val)
                    msg = "ok"
                latency_ms = int((time.monotonic() - start) * 1000)
                return {"ok": ok, "status": 0 if ok else None, "data": data if ok else {"error": msg}, "raw": data if ok else msg, "latency_ms": latency_ms}
            else:
                raise ValueError(f"Unsupported SNMP op: {op}")
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "status": None, "data": {"error": str(e)}, "raw": str(e), "latency_ms": latency_ms}

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self._run, request, timeout_s)

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("snmp transport does not support subscriptions.")

    async def close(self) -> None:
        return None
