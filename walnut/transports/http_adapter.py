"""
HTTP Transport Adapter.
"""
import logging
import time
import httpx
from typing import Dict, Any, Optional

from .base import TransportAdapter


logger = logging.getLogger(__name__)


class HttpAdapter:
    """
    A transport adapter for making HTTP requests using httpx.
    """
    name: str = "http"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout_s: float = 10.0

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        """
        Prepares the httpx client from the instance configuration.
        It looks for an 'http' block in the config, but falls back to top-level
        keys for backward compatibility.
        """
        http_config = instance_cfg.get("http", instance_cfg)

        base_url = http_config.get("base_url", "")
        headers = http_config.get("headers", {})
        verify = http_config.get("verify_tls", True)
        self._timeout_s = float(http_config.get("timeout_s", 10.0))

        logger.info(
            "Preparing HTTP adapter: base_url=%s verify_tls=%s timeout_s=%s",
            base_url,
            verify,
            self._timeout_s,
        )

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            verify=verify,
        )

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes an HTTP request.

        The request dict can contain:
        - method: (str) The HTTP method (e.g., 'GET', 'POST'). Defaults to 'GET'.
        - path: (str) The URL path. Defaults to '/'.
        - params: (dict) Query parameters.
        - json: (dict) JSON body for the request.
        """
        if not self._client:
            raise RuntimeError("HTTP adapter has not been prepared. Call prepare() first.")

        method = request.get("method", "GET")
        path = request.get("path", "/")
        params = request.get("params")
        json_data = request.get("json")

        start_time = time.monotonic()
        try:
            logger.debug("HTTP %s %s params=%s json=%s", method, path, params, bool(json_data))
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
                timeout=(timeout_s or self._timeout_s),
            )
            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Raise an exception for 4xx/5xx responses
            response.raise_for_status()

            try:
                # Try to parse JSON, fall back to text
                data = response.json()
            except Exception:
                data = response.text

            logger.info("HTTP %s %s -> %s in %dms", method, path, response.status_code, latency_ms)
            return {
                "ok": True,
                "status": response.status_code,
                "data": data,
                "raw": response.text,
                "latency_ms": latency_ms,
            }

        except httpx.HTTPStatusError as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "HTTP %s %s -> %s in %dms (HTTP error)",
                method,
                path,
                e.response.status_code if e.response else None,
                latency_ms,
            )
            return {
                "ok": False,
                "status": e.response.status_code,
                "data": {"error": "HTTP Status Error", "message": str(e)},
                "raw": e.response.text,
                "latency_ms": latency_ms,
            }
        except httpx.RequestError as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("HTTP %s %s failed in %dms: %s", method, path, latency_ms, e)
            return {
                "ok": False,
                "status": None,
                "data": {"error": f"HTTP Request Failed: {e.__class__.__name__}", "message": str(e)},
                "raw": str(e),
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception("HTTP %s %s failed in %dms: %s", method, path, latency_ms, e)
            return {
                "ok": False,
                "status": None,
                "data": {"error": "An unexpected error occurred", "message": str(e)},
                "raw": str(e),
                "latency_ms": latency_ms,
            }

    async def close(self) -> None:
        """
        Closes the httpx client.
        """
        if self._client:
            logger.info("Closing HTTP adapter client")
            await self._client.aclose()
            self._client = None
