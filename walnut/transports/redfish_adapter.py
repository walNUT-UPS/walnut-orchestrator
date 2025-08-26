"""
Redfish Transport Adapter.

Implements basic Redfish over HTTP using httpx. Supports session-based
authentication when username/password are provided; otherwise falls back
to basic authentication or anonymous access depending on BMC config.
"""
import time
from typing import Dict, Any, Optional

import httpx

from .base import TransportAdapter


class RedfishAdapter:
    """
    Redfish transport using HTTP(S).

    Config (from instance cfg under key 'redfish' or top-level):
    - base_url: e.g., https://bmc.example.com
    - verify_tls|verify_ssl: bool
    - username/password: for Redfish session auth
    - timeout_s: default request timeout

    Request for call():
    - method: GET/POST/DELETE/...
    - path: '/redfish/v1/...'
    - params/json: optional
    """
    name: str = "redfish"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout_s: float = 10.0
        self._session_location: Optional[str] = None

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        cfg = instance_cfg.get("redfish", instance_cfg)
        base_url = cfg.get("base_url", "")
        verify = cfg.get("verify_tls", cfg.get("verify_ssl", True))
        self._timeout_s = float(cfg.get("timeout_s", 10.0))

        username = cfg.get("username")
        password = cfg.get("password")

        headers: Dict[str, str] = {}
        auth: Optional[httpx.Auth] = None
        self._client = httpx.AsyncClient(base_url=base_url, headers=headers, verify=verify)

        # Try to create a Redfish Session if creds provided
        if username and password:
            try:
                resp = await self._client.post(
                    "/redfish/v1/SessionService/Sessions",
                    json={"UserName": username, "Password": password},
                    timeout=self._timeout_s,
                )
                if resp.status_code in (200, 201):
                    token = resp.headers.get("X-Auth-Token")
                    self._session_location = resp.headers.get("Location")
                    if token:
                        # Replace client with token header
                        await self._client.aclose()
                        self._client = httpx.AsyncClient(
                            base_url=base_url,
                            headers={"X-Auth-Token": token},
                            verify=verify,
                        )
                    else:
                        # Fall back to basic auth if token missing
                        auth = httpx.BasicAuth(username, password)
                else:
                    # Fallback to basic auth on failure
                    auth = httpx.BasicAuth(username, password)
            except Exception:
                auth = httpx.BasicAuth(username, password)

        if auth is not None:
            # Recreate client with basic auth
            if self._client:
                await self._client.aclose()
            self._client = httpx.AsyncClient(base_url=base_url, auth=auth, verify=verify)

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        if not self._client:
            raise RuntimeError("Redfish adapter has not been prepared. Call prepare() first.")

        method = request.get("method", "GET")
        path = request.get("path", "/redfish/v1/")
        params = request.get("params")
        json_data = request.get("json")

        start = time.monotonic()
        try:
            resp = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
                timeout=(timeout_s or self._timeout_s),
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            ok = 200 <= resp.status_code < 300
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return {
                "ok": ok,
                "status": resp.status_code,
                "data": data,
                "raw": resp.text,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "ok": False,
                "status": None,
                "data": {"error": f"Redfish request failed: {e.__class__.__name__}", "message": str(e)},
                "raw": str(e),
                "latency_ms": latency_ms,
            }

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("redfish transport does not support subscriptions.")

    async def close(self) -> None:
        # Best-effort logout if we created a session
        try:
            if self._client and self._session_location:
                try:
                    await self._client.delete(self._session_location, timeout=self._timeout_s)
                except Exception:
                    pass
        finally:
            if self._client:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
            self._client = None
            self._session_location = None

