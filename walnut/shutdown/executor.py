"""
Shutdown command execution with comprehensive logging and error handling.

Executes immediate shutdown commands on remote hosts via SSH with proper
timeout handling, retry logic, and detailed result tracking.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from walnut.database.connection import get_db_session
from walnut.database.models import Host, create_event
from walnut.hosts.manager import HostManager
from walnut.ssh.client import SSHCommandResult

logger = logging.getLogger(__name__)


class ShutdownStatus(Enum):
    """Shutdown operation status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ShutdownResult:
    """Result of a shutdown operation."""
    
    hostname: str
    ip_address: Optional[str]
    status: ShutdownStatus
    command: str
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None
    retry_count: int = 0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    @property
    def success(self) -> bool:
        """Whether shutdown was successful."""
        return self.status == ShutdownStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'status': self.status.value,
            'command': self.command,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'execution_time': self.execution_time,
            'error_message': self.error_message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'retry_count': self.retry_count,
            'success': self.success,
        }


class ShutdownExecutor:
    """
    Executes coordinated shutdown operations on managed hosts.
    
    Provides immediate shutdown execution with comprehensive logging,
    error handling, and result tracking for power event responses.
    """
    
    # Common shutdown commands by OS type
    SHUTDOWN_COMMANDS = {
        'linux': 'shutdown -P now',  # Power off immediately
        'freebsd': 'shutdown -p now',  # Power off immediately (TrueNAS)
        'windows': 'shutdown /s /t 0 /f',  # Force immediate shutdown
        'darwin': 'sudo shutdown -h now',  # macOS shutdown
        'default': 'shutdown -P now',  # Generic Linux command
    }
    
    def __init__(self, host_manager: Optional[HostManager] = None):
        self.host_manager = host_manager or HostManager()
        self._active_shutdowns: Dict[str, asyncio.Task] = {}
        self._results: List[ShutdownResult] = []
    
    def get_shutdown_command(self, host: Host, custom_command: Optional[str] = None) -> str:
        """
        Get appropriate shutdown command for a host.
        
        Args:
            host: Host to shutdown
            custom_command: Custom shutdown command override
            
        Returns:
            Shutdown command string
        """
        if custom_command:
            return custom_command
        
        # Check host metadata for custom command
        if host.host_metadata and 'shutdown_command' in host.host_metadata:
            return host.host_metadata['shutdown_command']
        
        # Use OS-specific command
        os_type = (host.os_type or 'default').lower()
        return self.SHUTDOWN_COMMANDS.get(os_type, self.SHUTDOWN_COMMANDS['default'])
    
    async def execute_shutdown(
        self,
        hostname: str,
        command: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 2,
        dry_run: bool = False,
    ) -> ShutdownResult:
        """
        Execute shutdown command on a specific host.
        
        Args:
            hostname: Host name to shutdown
            command: Custom shutdown command (uses default if None)
            timeout: Command timeout in seconds
            max_retries: Maximum retry attempts
            dry_run: If True, don't execute actual shutdown
            
        Returns:
            Shutdown operation result
        """
        start_time = datetime.now(timezone.utc)
        
        # Get host information
        host = await self.host_manager.get_host_by_name(hostname)
        if not host:
            return ShutdownResult(
                hostname=hostname,
                ip_address=None,
                status=ShutdownStatus.FAILED,
                command=command or "unknown",
                error_message=f"Host {hostname} not found",
                timestamp=start_time,
            )
        
        # Get shutdown command
        shutdown_command = self.get_shutdown_command(host, command)
        
        # Handle dry run
        if dry_run:
            logger.info(f"DRY RUN: Would execute '{shutdown_command}' on {hostname}")
            return ShutdownResult(
                hostname=hostname,
                ip_address=host.ip_address,
                status=ShutdownStatus.SUCCESS,
                command=f"DRY RUN: {shutdown_command}",
                exit_code=0,
                stdout="Dry run - command not executed",
                execution_time=0.1,
                timestamp=start_time,
            )
        
        # Execute with retries
        last_exception = None
        ssh_result: Optional[SSHCommandResult] = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Executing shutdown on {hostname} (attempt {attempt + 1}): {shutdown_command}")
                
                # Create SSH connection config
                config = await self.host_manager.ssh_client.connect_to_host(host)
                config.command_timeout = timeout
                
                # Execute command
                ssh_result = await self.host_manager.ssh_client.execute_command(
                    config, shutdown_command, timeout
                )
                
                # Check if shutdown was initiated successfully
                # Most shutdown commands return 0 immediately, even though the actual
                # shutdown happens asynchronously
                if ssh_result.exit_code == 0:
                    result = ShutdownResult(
                        hostname=hostname,
                        ip_address=host.ip_address,
                        status=ShutdownStatus.SUCCESS,
                        command=shutdown_command,
                        exit_code=ssh_result.exit_code,
                        stdout=ssh_result.stdout,
                        stderr=ssh_result.stderr,
                        execution_time=ssh_result.execution_time,
                        timestamp=start_time,
                        retry_count=attempt,
                    )
                    
                    logger.info(f"Shutdown initiated successfully on {hostname}")
                    await self._log_shutdown_event(result, "SHUTDOWN_SUCCESS")
                    return result
                
                else:
                    logger.warning(
                        f"Shutdown command returned non-zero exit code on {hostname}: "
                        f"{ssh_result.exit_code}"
                    )
                    
                    if attempt < max_retries:
                        await asyncio.sleep(1.0)  # Brief delay before retry
                        continue
                
            except asyncio.TimeoutError:
                logger.error(f"Shutdown command timed out on {hostname} after {timeout}s")
                result = ShutdownResult(
                    hostname=hostname,
                    ip_address=host.ip_address,
                    status=ShutdownStatus.TIMEOUT,
                    command=shutdown_command,
                    error_message=f"Command timed out after {timeout}s",
                    timestamp=start_time,
                    retry_count=attempt,
                )
                await self._log_shutdown_event(result, "SHUTDOWN_TIMEOUT")
                return result
                
            except Exception as e:
                last_exception = e
                logger.error(f"Shutdown failed on {hostname} (attempt {attempt + 1}): {e}")
                
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
        
        # All retries exhausted
        result = ShutdownResult(
            hostname=hostname,
            ip_address=host.ip_address,
            status=ShutdownStatus.FAILED,
            command=shutdown_command,
            exit_code=ssh_result.exit_code if ssh_result else None,
            stdout=ssh_result.stdout if ssh_result else None,
            stderr=ssh_result.stderr if ssh_result else None,
            execution_time=ssh_result.execution_time if ssh_result else None,
            error_message=str(last_exception) if last_exception else "Unknown error",
            timestamp=start_time,
            retry_count=max_retries,
        )
        
        await self._log_shutdown_event(result, "SHUTDOWN_FAILED")
        return result
    
    async def execute_mass_shutdown(
        self,
        hostnames: List[str],
        command: Optional[str] = None,
        timeout: int = 60,
        max_concurrent: int = 10,
        dry_run: bool = False,
    ) -> List[ShutdownResult]:
        """
        Execute shutdown on multiple hosts concurrently.
        
        Args:
            hostnames: List of host names to shutdown
            command: Custom shutdown command for all hosts
            timeout: Command timeout in seconds
            max_concurrent: Maximum concurrent shutdowns
            dry_run: If True, don't execute actual shutdowns
            
        Returns:
            List of shutdown results
        """
        if not hostnames:
            return []
        
        logger.info(f"Starting mass shutdown of {len(hostnames)} hosts")
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def shutdown_with_semaphore(hostname: str) -> ShutdownResult:
            async with semaphore:
                return await self.execute_shutdown(
                    hostname=hostname,
                    command=command,
                    timeout=timeout,
                    dry_run=dry_run,
                )
        
        # Execute shutdowns concurrently
        tasks = [shutdown_with_semaphore(hostname) for hostname in hostnames]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        shutdown_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Handle task exception
                shutdown_results.append(ShutdownResult(
                    hostname=hostnames[i],
                    ip_address=None,
                    status=ShutdownStatus.FAILED,
                    command=command or "unknown",
                    error_message=str(result),
                    timestamp=datetime.now(timezone.utc),
                ))
            else:
                shutdown_results.append(result)
        
        # Store results
        self._results.extend(shutdown_results)
        
        # Log summary
        successful = sum(1 for r in shutdown_results if r.success)
        failed = len(shutdown_results) - successful
        
        logger.info(f"Mass shutdown completed: {successful} successful, {failed} failed")
        
        # Create summary event
        await self._log_shutdown_event(
            shutdown_results[0] if shutdown_results else None,
            "MASS_SHUTDOWN_COMPLETED",
            metadata={
                'total_hosts': len(hostnames),
                'successful': successful,
                'failed': failed,
                'hostnames': hostnames,
                'dry_run': dry_run,
            }
        )
        
        return shutdown_results
    
    async def shutdown_by_priority(
        self,
        priority_groups: List[List[str]],
        command: Optional[str] = None,
        timeout: int = 60,
        group_delay: float = 5.0,
        dry_run: bool = False,
    ) -> List[ShutdownResult]:
        """
        Execute prioritized shutdown with groups and delays.
        
        Args:
            priority_groups: List of hostname groups in shutdown order
            command: Custom shutdown command
            timeout: Command timeout
            group_delay: Delay between groups (seconds)
            dry_run: If True, don't execute actual shutdowns
            
        Returns:
            List of all shutdown results
        """
        all_results = []
        
        for group_num, hostnames in enumerate(priority_groups, 1):
            if not hostnames:
                continue
            
            logger.info(f"Shutting down priority group {group_num}: {hostnames}")
            
            # Shutdown current group
            group_results = await self.execute_mass_shutdown(
                hostnames=hostnames,
                command=command,
                timeout=timeout,
                dry_run=dry_run,
            )
            
            all_results.extend(group_results)
            
            # Wait before next group (except for last group)
            if group_num < len(priority_groups) and group_delay > 0:
                logger.info(f"Waiting {group_delay}s before next priority group")
                await asyncio.sleep(group_delay)
        
        return all_results
    
    async def get_shutdown_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent shutdown operation history.
        
        Args:
            limit: Maximum number of results to return
            
        Returns:
            List of shutdown result dictionaries
        """
        # Return stored results
        recent_results = self._results[-limit:] if self._results else []
        return [result.to_dict() for result in recent_results]
    
    async def _log_shutdown_event(
        self,
        result: Optional[ShutdownResult],
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log shutdown operation as an event."""
        if not result and not metadata:
            return
        
        try:
            async with get_db_session() as session:
                # Determine severity
                if event_type.endswith('_SUCCESS'):
                    severity = "INFO"
                elif event_type.endswith('_FAILED') or event_type.endswith('_TIMEOUT'):
                    severity = "CRITICAL"
                else:
                    severity = "WARNING"
                
                # Create event metadata
                event_metadata = metadata or {}
                if result:
                    event_metadata.update(result.to_dict())
                
                # Create description
                if result:
                    description = f"Shutdown {result.status.value} on {result.hostname}"
                else:
                    description = f"Shutdown operation: {event_type}"
                
                # Create event
                event = create_event(
                    event_type=event_type,
                    description=description,
                    severity=severity,
                    metadata=event_metadata,
                )
                
                session.add(event)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to log shutdown event: {e}")
    
    def cancel_shutdown(self, hostname: str) -> bool:
        """
        Cancel active shutdown operation.
        
        Args:
            hostname: Host name to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        if hostname in self._active_shutdowns:
            task = self._active_shutdowns[hostname]
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled shutdown operation for {hostname}")
                return True
        
        return False
    
    def get_active_shutdowns(self) -> List[str]:
        """Get list of hosts with active shutdown operations."""
        return [
            hostname for hostname, task in self._active_shutdowns.items()
            if not task.done()
        ]
    
    async def emergency_shutdown_all(
        self,
        exclude_hosts: Optional[List[str]] = None,
        timeout: int = 30,
        dry_run: bool = False,
    ) -> List[ShutdownResult]:
        """
        Emergency shutdown of all managed SSH hosts.
        
        Args:
            exclude_hosts: Hostnames to exclude from shutdown
            timeout: Reduced timeout for emergency operations
            dry_run: If True, don't execute actual shutdowns
            
        Returns:
            List of shutdown results
        """
        exclude_hosts = exclude_hosts or []
        
        # Get all SSH hosts
        ssh_hosts = await self.host_manager.list_hosts(connection_type="ssh")
        hostnames = [
            host.hostname for host in ssh_hosts 
            if host.hostname not in exclude_hosts
        ]
        
        if not hostnames:
            logger.warning("No hosts available for emergency shutdown")
            return []
        
        logger.critical(f"EMERGENCY SHUTDOWN initiated for {len(hostnames)} hosts")
        
        # Execute with high concurrency and reduced timeout
        return await self.execute_mass_shutdown(
            hostnames=hostnames,
            timeout=timeout,
            max_concurrent=20,  # Higher concurrency for emergency
            dry_run=dry_run,
        )