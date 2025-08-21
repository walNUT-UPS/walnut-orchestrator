"""
Async SSH client for secure remote host connections.

Provides connection pooling, authentication, and command execution
with proper timeout handling and error recovery.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import asyncssh

from walnut.database.models import Host
from walnut.ssh.credentials import CredentialManager

logger = logging.getLogger(__name__)


@dataclass
class SSHConnectionConfig:
    """Configuration for SSH connections."""
    
    hostname: str
    port: int = 22
    username: Optional[str] = None
    password: Optional[str] = None
    private_key_path: Optional[str] = None
    private_key_data: Optional[bytes] = None
    connect_timeout: int = 30
    command_timeout: int = 60
    keepalive_interval: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class SSHCommandResult:
    """Result of SSH command execution."""
    
    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    success: bool
    retry_count: int = 0
    
    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        if self.stderr:
            return f"{self.stdout}\n{self.stderr}".strip()
        return self.stdout.strip()


class SSHConnectionPool:
    """
    Connection pool for SSH connections with automatic cleanup.
    
    Manages a pool of SSH connections to reduce connection overhead
    and improve performance for multiple operations on the same host.
    """
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self._connections: Dict[str, asyncssh.SSHClientConnection] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        self._last_used: Dict[str, float] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def _get_connection_key(self, config: SSHConnectionConfig) -> str:
        """Generate unique key for connection."""
        return f"{config.username}@{config.hostname}:{config.port}"
    
    async def get_connection(
        self, config: SSHConnectionConfig
    ) -> asyncssh.SSHClientConnection:
        """
        Get or create SSH connection from pool.
        
        Args:
            config: SSH connection configuration
            
        Returns:
            Active SSH connection
            
        Raises:
            asyncssh.Error: If connection fails
        """
        key = self._get_connection_key(config)
        
        # Get or create lock for this connection
        if key not in self._connection_locks:
            self._connection_locks[key] = asyncio.Lock()
        
        async with self._connection_locks[key]:
            # Check if we have a valid connection
            if key in self._connections:
                conn = self._connections[key]
                if not conn.is_closing():
                    self._last_used[key] = asyncio.get_event_loop().time()
                    return conn
                else:
                    # Clean up dead connection
                    del self._connections[key]
                    if key in self._last_used:
                        del self._last_used[key]
            
            # Create new connection
            logger.debug(f"Creating new SSH connection to {key}")
            conn = await self._create_connection(config)
            
            # Store in pool if we have space
            if len(self._connections) < self.max_connections:
                self._connections[key] = conn
                self._last_used[key] = asyncio.get_event_loop().time()
                
                # Start cleanup task if not running
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._cleanup_connections())
            
            return conn
    
    async def _create_connection(
        self, config: SSHConnectionConfig
    ) -> asyncssh.SSHClientConnection:
        """Create new SSH connection with proper authentication."""
        
        connect_kwargs = {
            'host': config.hostname,
            'port': config.port,
            'username': config.username,
            'connect_timeout': config.connect_timeout,
            'keepalive_interval': config.keepalive_interval,
            'server_host_key_algs': ['ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256'],
            'compression_algs': ['none'],  # Disable compression for speed
        }
        
        # Set authentication method
        if config.private_key_data:
            connect_kwargs['client_keys'] = [asyncssh.import_private_key(config.private_key_data)]
        elif config.private_key_path:
            key_path = Path(config.private_key_path).expanduser()
            if key_path.exists():
                connect_kwargs['client_keys'] = [str(key_path)]
            else:
                raise FileNotFoundError(f"SSH private key not found: {key_path}")
        elif config.password:
            connect_kwargs['password'] = config.password
        else:
            # Try default key locations
            default_keys = [
                Path.home() / '.ssh' / 'id_rsa',
                Path.home() / '.ssh' / 'id_ed25519',
                Path.home() / '.ssh' / 'id_ecdsa',
            ]
            
            available_keys = [str(k) for k in default_keys if k.exists()]
            if available_keys:
                connect_kwargs['client_keys'] = available_keys
        
        return await asyncssh.connect(**connect_kwargs)
    
    async def _cleanup_connections(self):
        """Periodic cleanup of idle connections."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                current_time = asyncio.get_event_loop().time()
                
                to_remove = []
                for key, last_used in self._last_used.items():
                    # Remove connections idle for more than 10 minutes
                    if current_time - last_used > 600:
                        to_remove.append(key)
                
                for key in to_remove:
                    if key in self._connections:
                        try:
                            self._connections[key].close()
                            await self._connections[key].wait_closed()
                        except Exception as e:
                            logger.warning(f"Error closing connection {key}: {e}")
                        finally:
                            self._connections.pop(key, None)
                            self._last_used.pop(key, None)
                            self._connection_locks.pop(key, None)
                
                if to_remove:
                    logger.debug(f"Cleaned up {len(to_remove)} idle SSH connections")
                
            except Exception as e:
                logger.error(f"Error in SSH connection cleanup: {e}")
    
    async def close_all(self):
        """Close all connections in the pool."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        for conn in self._connections.values():
            try:
                conn.close()
                await conn.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing SSH connection: {e}")
        
        self._connections.clear()
        self._last_used.clear()
        self._connection_locks.clear()


class SSHClient:
    """
    Async SSH client for remote host management.
    
    Provides secure connections with authentication, command execution,
    connection pooling, and proper error handling.
    """
    
    def __init__(
        self,
        credential_manager: Optional[CredentialManager] = None,
        max_connections: int = 10,
    ):
        self.credential_manager = credential_manager or CredentialManager()
        self.connection_pool = SSHConnectionPool(max_connections)
        self._shutdown_event = asyncio.Event()
    
    async def connect_to_host(
        self, host: Host, **kwargs
    ) -> SSHConnectionConfig:
        """
        Create SSH connection config for a host.
        
        Args:
            host: Host model with connection details
            **kwargs: Override connection parameters
            
        Returns:
            SSH connection configuration
            
        Raises:
            ValueError: If host configuration is invalid
        """
        config = SSHConnectionConfig(
            hostname=host.ip_address or host.hostname,
            **kwargs
        )
        
        # Load credentials if available
        if host.credentials_ref:
            try:
                credentials = await self.credential_manager.get_credentials(
                    host.credentials_ref
                )
                
                if 'username' in credentials:
                    config.username = credentials['username']
                if 'password' in credentials:
                    config.password = credentials['password']
                if 'private_key' in credentials:
                    pk = credentials['private_key']
                    if isinstance(pk, str):
                        config.private_key_data = pk.encode()
                    else:
                        config.private_key_data = pk
                if 'private_key_path' in credentials:
                    config.private_key_path = credentials['private_key_path']
                
            except Exception as e:
                logger.warning(f"Failed to load credentials for host {host.hostname}: {e}")
        
        return config
    
    @asynccontextmanager
    async def connection(self, config: SSHConnectionConfig):
        """
        Context manager for SSH connections.
        
        Args:
            config: SSH connection configuration
            
        Yields:
            SSH connection
        """
        conn = None
        try:
            conn = await self.connection_pool.get_connection(config)
            yield conn
        finally:
            # Connection is managed by pool, so we don't close it here
            pass
    
    async def execute_command(
        self,
        config: SSHConnectionConfig,
        command: str,
        timeout: Optional[int] = None,
    ) -> SSHCommandResult:
        """
        Execute command on remote host.
        
        Args:
            config: SSH connection configuration
            command: Command to execute
            timeout: Command timeout (uses config default if None)
            
        Returns:
            Command execution result
            
        Raises:
            asyncssh.Error: If SSH operation fails
            asyncio.TimeoutError: If command times out
        """
        timeout = timeout or config.command_timeout
        start_time = asyncio.get_event_loop().time()
        
        logger.debug(f"Executing SSH command on {config.hostname}: {command}")
        
        try:
            async with self.connection(config) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=timeout
                )
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return SSHCommandResult(
                    command=command,
                    exit_code=result.exit_status,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time=execution_time,
                    success=result.exit_status == 0,
                )
        
        except asyncio.TimeoutError:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"SSH command timed out after {timeout}s: {command}")
            raise
        
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"SSH command failed: {command} - {e}")
            raise
    
    async def execute_command_with_retry(
        self,
        config: SSHConnectionConfig,
        command: str,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> SSHCommandResult:
        """
        Execute command with automatic retry on failure.
        
        Args:
            config: SSH connection configuration
            command: Command to execute
            max_retries: Maximum retry attempts (uses config default if None)
            retry_delay: Delay between retries (uses config default if None)
            
        Returns:
            Command execution result
            
        Raises:
            Exception: If all retries are exhausted
        """
        max_retries = max_retries or config.max_retries
        retry_delay = retry_delay or config.retry_delay
        
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                result = await self.execute_command(config, command)
                result.retry_count = attempt
                return result
            
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    logger.warning(
                        f"SSH command failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"SSH command failed after {max_retries + 1} attempts: {e}")
        
        if last_exception:
            raise last_exception
    
    async def test_connection(self, config: SSHConnectionConfig) -> bool:
        """
        Test SSH connection to host.
        
        Args:
            config: SSH connection configuration
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            result = await self.execute_command(config, "echo 'connection_test'", timeout=10)
            return result.success and "connection_test" in result.stdout
        except Exception as e:
            logger.debug(f"SSH connection test failed: {e}")
            return False
    
    async def get_host_info(self, config: SSHConnectionConfig) -> Dict[str, Any]:
        """
        Get basic host information via SSH.
        
        Args:
            config: SSH connection configuration
            
        Returns:
            Dictionary with host information
        """
        info = {}
        
        commands = {
            'hostname': 'hostname',
            'uptime': 'uptime',
            'uname': 'uname -a',
            'load': 'cat /proc/loadavg 2>/dev/null || uptime | awk -F"load average:" "{print $2}"',
            'memory': 'free -m 2>/dev/null || vm_stat | head -10',
            'disk': 'df -h / 2>/dev/null || df -h',
        }
        
        for key, command in commands.items():
            try:
                result = await self.execute_command(config, command, timeout=10)
                if result.success:
                    info[key] = result.stdout.strip()
                else:
                    info[key] = None
            except Exception as e:
                logger.debug(f"Failed to get {key} info: {e}")
                info[key] = None
        
        return info
    
    async def shutdown(self):
        """Shutdown SSH client and close all connections."""
        self._shutdown_event.set()
        await self.connection_pool.close_all()


# Global SSH client instance
_ssh_client: Optional[SSHClient] = None


def get_ssh_client() -> SSHClient:
    """Get global SSH client instance."""
    global _ssh_client
    if _ssh_client is None:
        _ssh_client = SSHClient()
    return _ssh_client


async def shutdown_ssh_client():
    """Shutdown global SSH client."""
    global _ssh_client
    if _ssh_client is not None:
        await _ssh_client.shutdown()
        _ssh_client = None