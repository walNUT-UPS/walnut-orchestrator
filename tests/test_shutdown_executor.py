"""
Tests for shutdown executor functionality.

Tests shutdown command execution, mass shutdown operations, and 
integration with the host management system.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from walnut.shutdown.executor import (
    ShutdownExecutor,
    ShutdownResult,
    ShutdownStatus,
)
from walnut.database.models import create_host
from walnut.hosts.manager import HostManager
from walnut.ssh.client import SSHCommandResult


class TestShutdownStatus:
    """Test shutdown status enumeration."""
    
    def test_status_values(self):
        assert ShutdownStatus.PENDING.value == "pending"
        assert ShutdownStatus.IN_PROGRESS.value == "in_progress"
        assert ShutdownStatus.SUCCESS.value == "success"
        assert ShutdownStatus.FAILED.value == "failed"
        assert ShutdownStatus.TIMEOUT.value == "timeout"
        assert ShutdownStatus.CANCELLED.value == "cancelled"


class TestShutdownResult:
    """Test shutdown result data structure."""
    
    def test_successful_result_creation(self):
        result = ShutdownResult(
            hostname="test-host",
            ip_address="192.168.1.100",
            status=ShutdownStatus.SUCCESS,
            command="shutdown -P now",
            exit_code=0,
            execution_time=1.5,
        )
        
        assert result.hostname == "test-host"
        assert result.success is True
        assert result.status == ShutdownStatus.SUCCESS
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)
    
    def test_failed_result_creation(self):
        result = ShutdownResult(
            hostname="test-host",
            ip_address="192.168.1.100",
            status=ShutdownStatus.FAILED,
            command="shutdown -P now",
            exit_code=1,
            error_message="Permission denied",
        )
        
        assert result.hostname == "test-host"
        assert result.success is False
        assert result.error_message == "Permission denied"
    
    def test_result_to_dict(self):
        result = ShutdownResult(
            hostname="test-host",
            ip_address="192.168.1.100",
            status=ShutdownStatus.SUCCESS,
            command="shutdown -P now",
            exit_code=0,
            retry_count=1,
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['hostname'] == "test-host"
        assert result_dict['status'] == "success"
        assert result_dict['success'] is True
        assert result_dict['retry_count'] == 1
        assert 'timestamp' in result_dict


class TestShutdownExecutor:
    """Test shutdown executor operations."""
    
    @pytest.fixture
    def mock_host_manager(self):
        return MagicMock(spec=HostManager)
    
    @pytest.fixture
    def executor(self, mock_host_manager):
        return ShutdownExecutor(host_manager=mock_host_manager)
    
    @pytest.fixture
    def mock_host(self):
        return create_host(
            hostname="test-server",
            ip_address="192.168.1.100",
            os_type="linux",
            connection_type="ssh",
        )
    
    def test_executor_initialization(self, executor):
        assert executor.host_manager is not None
        assert len(executor._active_shutdowns) == 0
        assert len(executor._results) == 0
    
    def test_get_shutdown_command_by_os(self, executor, mock_host):
        # Test Linux command
        mock_host.os_type = "linux"
        command = executor.get_shutdown_command(mock_host)
        assert command == "shutdown -P now"
        
        # Test FreeBSD command (TrueNAS)
        mock_host.os_type = "freebsd"
        command = executor.get_shutdown_command(mock_host)
        assert command == "shutdown -p now"
        
        # Test Windows command
        mock_host.os_type = "windows"
        command = executor.get_shutdown_command(mock_host)
        assert command == "shutdown /s /t 0 /f"
        
        # Test default command
        mock_host.os_type = None
        command = executor.get_shutdown_command(mock_host)
        assert command == "shutdown -P now"
    
    def test_get_shutdown_command_custom_override(self, executor, mock_host):
        custom_command = "poweroff"
        command = executor.get_shutdown_command(mock_host, custom_command)
        assert command == custom_command
    
    def test_get_shutdown_command_from_metadata(self, executor, mock_host):
        mock_host.host_metadata = {"shutdown_command": "halt"}
        command = executor.get_shutdown_command(mock_host)
        assert command == "halt"
    
    @pytest.mark.asyncio
    async def test_execute_shutdown_host_not_found(self, executor, mock_host_manager):
        mock_host_manager.get_host_by_name.return_value = None
        
        result = await executor.execute_shutdown("nonexistent-host")
        
        assert result.status == ShutdownStatus.FAILED
        assert result.hostname == "nonexistent-host"
        assert "not found" in result.error_message
    
    @pytest.mark.asyncio
    async def test_execute_shutdown_dry_run(self, executor, mock_host_manager, mock_host):
        mock_host_manager.get_host_by_name.return_value = mock_host
        
        result = await executor.execute_shutdown("test-server", dry_run=True)
        
        assert result.status == ShutdownStatus.SUCCESS
        assert result.hostname == "test-server"
        assert "DRY RUN" in result.command
        assert "not executed" in result.stdout
        assert result.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_shutdown_success(self, executor, mock_host_manager, mock_host):
        # Setup mocks
        mock_host_manager.get_host_by_name.return_value = mock_host
        
        mock_ssh_result = SSHCommandResult(
            command="shutdown -P now",
            exit_code=0,
            stdout="Shutdown initiated",
            stderr="",
            execution_time=0.5,
            success=True,
        )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.return_value = mock_ssh_result
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        result = await executor.execute_shutdown("test-server")
        
        assert result.status == ShutdownStatus.SUCCESS
        assert result.exit_code == 0
        assert result.stdout == "Shutdown initiated"
        assert result.execution_time == 0.5
    
    @pytest.mark.asyncio
    async def test_execute_shutdown_failure(self, executor, mock_host_manager, mock_host):
        # Setup mocks for failed shutdown
        mock_host_manager.get_host_by_name.return_value = mock_host
        
        mock_ssh_result = SSHCommandResult(
            command="shutdown -P now",
            exit_code=1,
            stdout="",
            stderr="Permission denied",
            execution_time=0.1,
            success=False,
        )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.return_value = mock_ssh_result
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        result = await executor.execute_shutdown("test-server")
        
        assert result.status == ShutdownStatus.FAILED
        assert result.exit_code == 1
        assert result.stderr == "Permission denied"
    
    @pytest.mark.asyncio
    async def test_execute_shutdown_timeout(self, executor, mock_host_manager, mock_host):
        # Setup mocks for timeout
        mock_host_manager.get_host_by_name.return_value = mock_host
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.side_effect = asyncio.TimeoutError()
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        result = await executor.execute_shutdown("test-server", timeout=1)
        
        assert result.status == ShutdownStatus.TIMEOUT
        assert "timed out" in result.error_message
    
    @pytest.mark.asyncio
    async def test_execute_mass_shutdown_empty_list(self, executor):
        results = await executor.execute_mass_shutdown([])
        assert results == []
    
    @pytest.mark.asyncio
    async def test_execute_mass_shutdown_single_host(self, executor, mock_host_manager, mock_host):
        # Setup successful shutdown
        mock_host_manager.get_host_by_name.return_value = mock_host
        
        mock_ssh_result = SSHCommandResult(
            command="shutdown -P now",
            exit_code=0,
            stdout="Shutdown initiated",
            stderr="",
            execution_time=0.5,
            success=True,
        )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.return_value = mock_ssh_result
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        results = await executor.execute_mass_shutdown(["test-server"])
        
        assert len(results) == 1
        assert results[0].status == ShutdownStatus.SUCCESS
        assert results[0].hostname == "test-server"
    
    @pytest.mark.asyncio
    async def test_execute_mass_shutdown_multiple_hosts(self, executor, mock_host_manager):
        # Setup multiple hosts
        host1 = create_host(hostname="server1", ip_address="192.168.1.101")
        host2 = create_host(hostname="server2", ip_address="192.168.1.102")
        
        def mock_get_host(hostname):
            if hostname == "server1":
                return host1
            elif hostname == "server2":
                return host2
            return None
        
        mock_host_manager.get_host_by_name.side_effect = mock_get_host
        
        # Mock SSH results - server1 succeeds, server2 fails
        def mock_execute_command(config, command, timeout=None):
            if "192.168.1.101" in str(config.hostname):
                return SSHCommandResult(
                    command=command, exit_code=0, stdout="OK", stderr="",
                    execution_time=0.3, success=True
                )
            else:
                return SSHCommandResult(
                    command=command, exit_code=1, stdout="", stderr="Failed",
                    execution_time=0.1, success=False
                )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.side_effect = mock_execute_command
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        results = await executor.execute_mass_shutdown(["server1", "server2"])
        
        assert len(results) == 2
        
        # Find results by hostname
        server1_result = next(r for r in results if r.hostname == "server1")
        server2_result = next(r for r in results if r.hostname == "server2")
        
        assert server1_result.status == ShutdownStatus.SUCCESS
        assert server2_result.status == ShutdownStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_shutdown_by_priority(self, executor, mock_host_manager):
        # Test prioritized shutdown with multiple groups
        host1 = create_host(hostname="critical-server")
        host2 = create_host(hostname="normal-server")
        
        def mock_get_host(hostname):
            if hostname == "critical-server":
                return host1
            elif hostname == "normal-server":
                return host2
            return None
        
        mock_host_manager.get_host_by_name.side_effect = mock_get_host
        
        # Mock successful shutdowns
        mock_ssh_result = SSHCommandResult(
            command="shutdown -P now", exit_code=0, stdout="OK", stderr="",
            execution_time=0.2, success=True
        )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.return_value = mock_ssh_result
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        # Define priority groups
        priority_groups = [
            ["critical-server"],  # Group 1: Critical systems first
            ["normal-server"],    # Group 2: Normal systems second
        ]
        
        start_time = asyncio.get_event_loop().time()
        results = await executor.shutdown_by_priority(
            priority_groups=priority_groups,
            group_delay=0.1,  # Short delay for testing
        )
        end_time = asyncio.get_event_loop().time()
        
        assert len(results) == 2
        assert all(r.status == ShutdownStatus.SUCCESS for r in results)
        
        # Should have taken at least the group delay time
        assert (end_time - start_time) >= 0.1
    
    @pytest.mark.asyncio
    async def test_emergency_shutdown_all(self, executor, mock_host_manager):
        # Setup mock hosts
        host1 = create_host(hostname="server1", connection_type="ssh")
        host2 = create_host(hostname="server2", connection_type="ssh")
        host3 = create_host(hostname="excluded", connection_type="ssh")
        
        mock_host_manager.list_hosts.return_value = [host1, host2, host3]
        
        def mock_get_host(hostname):
            hosts = {"server1": host1, "server2": host2, "excluded": host3}
            return hosts.get(hostname)
        
        mock_host_manager.get_host_by_name.side_effect = mock_get_host
        
        # Mock successful shutdowns
        mock_ssh_result = SSHCommandResult(
            command="shutdown -P now", exit_code=0, stdout="Emergency shutdown",
            stderr="", execution_time=0.2, success=True
        )
        
        mock_ssh_client = AsyncMock()
        mock_ssh_client.connect_to_host.return_value = MagicMock()
        mock_ssh_client.execute_command.return_value = mock_ssh_result
        
        mock_host_manager.ssh_client = mock_ssh_client
        
        # Execute emergency shutdown excluding one host
        results = await executor.emergency_shutdown_all(
            exclude_hosts=["excluded"],
            timeout=30,
        )
        
        assert len(results) == 2
        hostnames = [r.hostname for r in results]
        assert "server1" in hostnames
        assert "server2" in hostnames
        assert "excluded" not in hostnames
        assert all(r.status == ShutdownStatus.SUCCESS for r in results)
    
    def test_get_active_shutdowns(self, executor):
        # Initially no active shutdowns
        active = executor.get_active_shutdowns()
        assert active == []
        
        # Add a fake active task
        fake_task = MagicMock()
        fake_task.done.return_value = False
        executor._active_shutdowns["test-host"] = fake_task
        
        active = executor.get_active_shutdowns()
        assert "test-host" in active
    
    def test_cancel_shutdown(self, executor):
        # Test canceling non-existent shutdown
        result = executor.cancel_shutdown("nonexistent")
        assert result is False
        
        # Test canceling active shutdown
        fake_task = MagicMock()
        fake_task.done.return_value = False
        executor._active_shutdowns["test-host"] = fake_task
        
        result = executor.cancel_shutdown("test-host")
        assert result is True
        fake_task.cancel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_shutdown_history(self, executor):
        # Add some fake results
        result1 = ShutdownResult("host1", "1.1.1.1", ShutdownStatus.SUCCESS, "shutdown")
        result2 = ShutdownResult("host2", "1.1.1.2", ShutdownStatus.FAILED, "shutdown")
        
        executor._results = [result1, result2]
        
        history = await executor.get_shutdown_history()
        
        assert len(history) == 2
        assert all(isinstance(item, dict) for item in history)
        assert history[0]['hostname'] == "host1"
        assert history[1]['hostname'] == "host2"
    
    @pytest.mark.asyncio
    async def test_get_shutdown_history_with_limit(self, executor):
        # Add more results than the limit
        for i in range(5):
            result = ShutdownResult(f"host{i}", f"1.1.1.{i}", ShutdownStatus.SUCCESS, "shutdown")
            executor._results.append(result)
        
        history = await executor.get_shutdown_history(limit=3)
        
        # Should return last 3 results
        assert len(history) == 3
        assert history[0]['hostname'] == "host2"  # Last 3: host2, host3, host4
        assert history[2]['hostname'] == "host4"


@pytest.mark.integration  
class TestShutdownExecutorIntegration:
    """Integration tests for shutdown executor."""
    
    @pytest.mark.asyncio
    async def test_shutdown_result_event_logging(self):
        """Test that shutdown results are properly logged as events."""
        # This would test integration with the database event system
        # For now, just test that the result structure is correct
        
        result = ShutdownResult(
            hostname="integration-test",
            ip_address="127.0.0.1",
            status=ShutdownStatus.SUCCESS,
            command="echo test",
            exit_code=0,
            execution_time=0.1,
        )
        
        result_dict = result.to_dict()
        
        # Verify all required fields are present for event logging
        required_fields = [
            'hostname', 'status', 'command', 'timestamp', 
            'success', 'execution_time'
        ]
        
        for field in required_fields:
            assert field in result_dict
        
        # Verify data types
        assert isinstance(result_dict['success'], bool)
        assert isinstance(result_dict['execution_time'], (int, float))
        assert isinstance(result_dict['timestamp'], str)  # ISO format


if __name__ == "__main__":
    pytest.main([__file__, "-v"])