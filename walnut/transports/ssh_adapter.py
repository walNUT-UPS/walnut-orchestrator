"""
SSH Transport Adapter using Paramiko.
"""
import time
import anyio
import paramiko
from typing import Dict, Any, Optional, List

from .base import TransportAdapter


class SshAdapter:
    """
    A transport adapter for executing commands over SSH using Paramiko.

    Each `call` creates a new SSH connection, executes the commands, and
    closes the connection.
    """
    name: str = "ssh"

    def __init__(self):
        self._config: Dict[str, Any] = {}

    async def prepare(self, instance_cfg: Dict[str, Any]) -> None:
        """
        Stores the SSH connection configuration from the 'ssh' block or top-level.
        """
        self._config = instance_cfg.get("ssh", instance_cfg)

    def _execute_ssh_commands(
        self,
        commands: List[str],
        timeout_s: float
    ) -> Dict[str, Any]:
        """
        This synchronous function runs in a separate thread to avoid blocking
        the asyncio event loop. It connects, executes commands, and disconnects.
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        host = self._config.get("host")
        port = int(self._config.get("port", 22))
        username = self._config.get("username")
        password = self._config.get("password")
        key_filename = self._config.get("key_filename") # Placeholder for key-based auth

        if not host or not username:
            raise ValueError("SSH 'host' and 'username' are required in config.")

        try:
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                key_filename=key_filename,
                timeout=timeout_s,
            )

            # Note: `exec_command` is simple and does not support interactive sessions,
            # 'enable' modes, or complex prompt handling. For that, a shell-based
            # approach (`invoke_shell`) would be needed.

            full_output = ""
            for cmd in commands:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout_s)
                exit_code = stdout.channel.recv_exit_status()
                output = stdout.read().decode('utf-8', errors='ignore')
                error = stderr.read().decode('utf-8', errors='ignore')

                full_output += f"--- CMD: {cmd} ---\n"
                full_output += output
                if error:
                    full_output += f"\n--- STDERR ---\n{error}"

                if exit_code != 0:
                    # This approach stops at the first failing command.
                    raise RuntimeError(f"Command '{cmd}' failed with exit code {exit_code}:\n{error}")

            return {
                "ok": True,
                "status": 0,  # Using 0 for success, mimicking shell exit codes
                "data": {"output": full_output},
                "raw": full_output,
            }

        except Exception as e:
            return {
                "ok": False,
                "status": None,
                "data": {"error": f"SSH operation failed: {e.__class__.__name__}", "message": str(e)},
                "raw": str(e),
            }
        finally:
            if client:
                client.close()

    async def call(self, request: Dict[str, Any], *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes one or more SSH commands by running a sync Paramiko session
        in a separate thread.

        Request dict must contain:
        - commands: (list[str]) A list of shell commands to execute in order.
        """
        commands = request.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError("'commands' must be a non-empty list of strings.")

        op_timeout = timeout_s or float(self._config.get("timeout_s", 15.0))

        start_time = time.monotonic()

        try:
            result = await anyio.to_thread.run_sync(
                self._execute_ssh_commands,
                commands,
                op_timeout
            )
        except Exception as e:
            result = {
                "ok": False,
                "status": None,
                "data": {"error": f"SSH task execution failed: {e.__class__.__name__}", "message": str(e)},
                "raw": str(e),
            }

        latency_ms = int((time.monotonic() - start_time) * 1000)
        result["latency_ms"] = latency_ms

        return result

    async def close(self) -> None:
        """
        No-op for this adapter, as connections are created and destroyed per-call.
        """
        pass
