"""
Telnet Transport Adapter using Python's standard library.

Provides simple command execution over Telnet for devices that expose
line-oriented shells. This is intentionally minimal and best-effort.
"""
import time
import telnetlib
from typing import Dict, Any, Optional, List

import anyio

from .base import TransportAdapter


class TelnetAdapter:
    """
    A transport adapter for executing commands over Telnet.

    Request format for call():
    - commands: list[str] commands to send
    - prompt: optional str/bytes to wait for after each command (default: ">" or "#")
    - login: optional dict with keys {username, password, username_prompt, password_prompt}
    - read_timeout_s: optional float per read timeout (default from config or 10s)
    """
    name: str = "telnet"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        # Allow nested block or top-level
        self._config = instance_cfg.get("telnet", instance_cfg)

    def _run_telnet(self, commands: List[str], prompt: Optional[bytes], read_timeout: float) -> Dict[str, Any]:
        host = self._config.get("host")
        port = int(self._config.get("port", 23))
        username = self._config.get("username")
        password = self._config.get("password")
        login_cfg = self._config.get("login", {})

        # Request can override login config
        if isinstance(login_cfg, dict):
            username = login_cfg.get("username", username)
            password = login_cfg.get("password", password)

        username_prompt = (login_cfg.get("username_prompt") or "login:").encode()
        password_prompt = (login_cfg.get("password_prompt") or "Password:").encode()

        if not host:
            raise ValueError("Telnet 'host' is required in config.")

        tn: Optional[telnetlib.Telnet] = None
        start = time.monotonic()
        try:
            tn = telnetlib.Telnet(host, port, timeout=read_timeout)

            # Basic login flow if credentials provided
            if username:
                try:
                    tn.read_until(username_prompt, timeout=read_timeout)
                    tn.write((username + "\n").encode())
                except EOFError:
                    # Some devices don't prompt, try sending anyway
                    tn.write((username + "\n").encode())
                if password is not None:
                    try:
                        tn.read_until(password_prompt, timeout=read_timeout)
                    except EOFError:
                        pass
                    tn.write((password + "\n").encode())

            # Default prompt heuristics
            if prompt is None:
                prompt = b"#"

            full_output = b""
            for cmd in commands:
                tn.write((cmd + "\n").encode())
                try:
                    chunk = tn.read_until(prompt, timeout=read_timeout)
                except EOFError:
                    chunk = b""
                full_output += b"--- CMD: " + cmd.encode() + b" ---\n" + chunk

            latency_ms = int((time.monotonic() - start) * 1000)
            text = full_output.decode("utf-8", errors="ignore")
            return {
                "ok": True,
                "status": 0,
                "data": {"output": text},
                "raw": text,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "ok": False,
                "status": None,
                "data": {"error": f"Telnet operation failed: {e.__class__.__name__}", "message": str(e)},
                "raw": str(e),
                "latency_ms": latency_ms,
            }
        finally:
            try:
                if tn:
                    tn.close()
            except Exception:
                pass

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        commands = request.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError("'commands' must be a non-empty list of strings.")
        prompt = request.get("prompt")
        if isinstance(prompt, str):
            prompt_b = prompt.encode()
        elif isinstance(prompt, (bytes, bytearray)):
            prompt_b = bytes(prompt)
        else:
            prompt_b = None

        read_timeout = float(request.get("read_timeout_s") or self._config.get("timeout_s", 10.0))

        return await anyio.to_thread.run_sync(self._run_telnet, commands, prompt_b, read_timeout)

    def subscribe(self, request: Dict[str, Any], on_event):  # type: ignore[override]
        raise NotImplementedError("telnet transport does not support subscriptions.")

    async def close(self) -> None:
        # No persistent resources
        return None

