"""
Tests for SSH client functionality.

Tests SSH connections, command execution, and integration with
the walNUT host management system.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from walnut.ssh.client import (
    SSHClient,
    SSHConnectionConfig,
    SSHCommandResult,
    SSHConnectionPool,
    get_ssh_client,
    shutdown_ssh_client,
)
from walnut.ssh.credentials import CredentialManager
from walnut.database.models import Host, create_host


class TestSSHConnectionConfig:
    """Test SSH connection configuration."""
    
    def test_basic_config_creation(self):
        config = SSHConnectionConfig(hostname="test.example.com")
        
        assert config.hostname == "test.example.com"
        assert config.port == 22
        assert config.connect_timeout == 30
        assert config.command_timeout == 60
        assert config.max_retries == 3
    
    def test_config_with_custom_values(self):
        config = SSHConnectionConfig(
            hostname="192.168.1.100",
            port=2222,
            username="admin",
            password="secret",
            connect_timeout=15,
            command_timeout=120,
        )
        
        assert config.hostname == "192.168.1.100"
        assert config.port == 2222
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.connect_timeout == 15
        assert config.command_timeout == 120


class TestSSHCommandResult:
    """Test SSH command result handling."""
    
    def test_successful_result(self):
        result = SSHCommandResult(
            command="echo 'test'",
            exit_code=0,
            stdout="test\n",
            stderr="",
            execution_time=0.1,
            success=True,
        )
        
        assert result.success is True
        assert result.output == "test"  # .strip() removes the \n
        assert result.command == "echo 'test'"
    
    def test_failed_result_with_stderr(self):
        result = SSHCommandResult(
            command="invalid_command",
            exit_code=127,
            stdout="",
            stderr="command not found",
            execution_time=0.05,
            success=False,
        )
        
        assert result.success is False
        assert "command not found" in result.output
        assert result.exit_code == 127
    
    def test_result_with_both_outputs(self):
        result = SSHCommandResult(
            command="ls /nonexistent",
            exit_code=2,
            stdout="some output",
            stderr="No such file or directory",
            execution_time=0.2,
            success=False,
        )
        
        expected_output = "some output\nNo such file or directory"
        assert result.output == expected_output


class TestSSHConnectionPool:
    """Test SSH connection pooling."""
    
    @pytest.fixture
    def pool(self):
        return SSHConnectionPool(max_connections=3)
    
    def test_pool_initialization(self, pool):
        assert pool.max_connections == 3
        assert len(pool._connections) == 0
        assert len(pool._connection_locks) == 0
    
    def test_connection_key_generation(self, pool):
        config = SSHConnectionConfig(
            hostname="test.com",
            port=22,
            username="user",
        )
        
        key = pool._get_connection_key(config)
        assert key == "user@test.com:22"
    
    @pytest.mark.asyncio
    async def test_connection_pool_cleanup(self, pool):
        # Test that cleanup task can be started and stopped
        pool._cleanup_task = asyncio.create_task(pool._cleanup_connections())
        
        # Let it run briefly
        await asyncio.sleep(0.01)
        
        # Stop cleanup
        await pool.close_all()
        
        # The task should be cancelled or completed
        assert pool._cleanup_task.cancelled() or pool._cleanup_task.done()


@pytest.mark.asyncio
class TestSSHClient:
    """Test SSH client operations."""
    
    @pytest.fixture
    def ssh_client(self):
        return SSHClient()
    
    @pytest.fixture
    def mock_host(self):
        return create_host(
            hostname="test-host",
            ip_address="192.168.1.100",
            os_type="linux",
            connection_type="ssh",
            metadata={"ssh_port": 22},
        )
    
    async def test_client_initialization(self, ssh_client):
        assert ssh_client.connection_pool is not None
        assert ssh_client.credential_manager is not None
        assert not ssh_client._shutdown_event.is_set()
    
    async def test_connect_to_host_basic(self, ssh_client, mock_host):
        config = await ssh_client.connect_to_host(mock_host)
        
        assert config.hostname == "192.168.1.100"
        assert config.port == 22
    
    async def test_connect_to_host_with_override(self, ssh_client, mock_host):
        config = await ssh_client.connect_to_host(
            mock_host,
            port=2222,
            username="custom_user",
        )
        
        assert config.hostname == "192.168.1.100"
        assert config.port == 2222
        assert config.username == "custom_user"
    
    async def test_execute_command_success(self, ssh_client):
        # Mock successful SSH execution
        mock_result = MagicMock()
        mock_result.exit_status = 0
        mock_result.stdout = "command output"
        mock_result.stderr = ""
        
        mock_conn = AsyncMock()
        mock_conn.run.return_value = mock_result
        mock_conn.is_closing.return_value = False
        
        # Directly mock the connection pool
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        result = await ssh_client.execute_command(config, "echo 'test'")
        
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "command output"
        assert result.command == "echo 'test'"
        assert result.execution_time > 0
    
    async def test_execute_command_failure(self, ssh_client):
        # Mock failed SSH execution
        mock_result = MagicMock()
        mock_result.exit_status = 1
        mock_result.stdout = ""
        mock_result.stderr = "command failed"
        
        mock_conn = AsyncMock()
        mock_conn.run.return_value = mock_result
        mock_conn.is_closing.return_value = False
        
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        result = await ssh_client.execute_command(config, "false")
        
        assert result.success is False
        assert result.exit_code == 1
        assert result.stderr == "command failed"
    
    async def test_execute_command_timeout(self, ssh_client):
        # Mock timeout during command execution
        mock_conn = AsyncMock()
        mock_conn.run.side_effect = asyncio.TimeoutError()
        mock_conn.is_closing.return_value = False
        
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        
        with pytest.raises(asyncio.TimeoutError):
            await ssh_client.execute_command(config, "sleep 100", timeout=1)
    
    async def test_execute_command_with_retry(self, ssh_client):
        # Mock connection that fails twice then succeeds
        call_count = 0
        
        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                raise ConnectionError("Connection failed")
            
            # Third attempt succeeds
            result = MagicMock()
            result.exit_status = 0
            result.stdout = "success"
            result.stderr = ""
            return result
        
        mock_conn = AsyncMock()
        mock_conn.run.side_effect = mock_run
        mock_conn.is_closing.return_value = False
        
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test", max_retries=3)
        result = await ssh_client.execute_command_with_retry(config, "test command")
        
        assert result.success is True
        assert result.retry_count == 2  # Failed twice, succeeded on third
        assert call_count == 3
    
    async def test_test_connection_success(self, ssh_client):
        mock_result = MagicMock()
        mock_result.exit_status = 0
        mock_result.stdout = "connection_test\n"
        mock_result.stderr = ""
        
        mock_conn = AsyncMock()
        mock_conn.run.return_value = mock_result
        mock_conn.is_closing.return_value = False
        
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        success = await ssh_client.test_connection(config)
        
        assert success is True
    
    async def test_test_connection_failure(self, ssh_client):
        ssh_client.connection_pool.get_connection = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        success = await ssh_client.test_connection(config)
        
        assert success is False
    
    async def test_get_host_info(self, ssh_client):
        # Mock responses for different info commands
        def mock_run(command, **kwargs):
            result = MagicMock()
            result.exit_status = 0
            result.stderr = ""
            
            if "hostname" in command:
                result.stdout = "test-server"
            elif "uptime" in command:
                result.stdout = "up 5 days, 10:30"
            elif "uname" in command:
                result.stdout = "Linux test-server 5.4.0 #1 SMP"
            else:
                result.stdout = "info not available"
            
            return result
        
        mock_conn = AsyncMock()
        mock_conn.run.side_effect = mock_run
        mock_conn.is_closing.return_value = False
        
        ssh_client.connection_pool.get_connection = AsyncMock(return_value=mock_conn)
        
        config = SSHConnectionConfig(hostname="test.com", username="test")
        info = await ssh_client.get_host_info(config)
        
        assert info['hostname'] == "test-server"
        assert info['uptime'] == "up 5 days, 10:30"
        assert "Linux" in info['uname']
    
    async def test_shutdown(self, ssh_client):
        # Test graceful shutdown
        await ssh_client.shutdown()
        
        assert ssh_client._shutdown_event.is_set()
        # Connection pool should be closed
        assert len(ssh_client.connection_pool._connections) == 0


class TestGlobalSSHClient:
    """Test global SSH client management."""
    
    def test_get_ssh_client_singleton(self):
        # First call creates client
        client1 = get_ssh_client()
        assert client1 is not None
        
        # Second call returns same client
        client2 = get_ssh_client()
        assert client1 is client2
    
    @pytest.mark.asyncio
    async def test_shutdown_global_client(self):
        # Get client and shutdown
        client = get_ssh_client()
        await shutdown_ssh_client()
        
        # Should create new client on next call
        new_client = get_ssh_client()
        assert new_client is not client


@pytest.mark.integration
class TestSSHClientIntegration:
    """Integration tests for SSH client with real operations."""
    
    @pytest.fixture
    def temp_key_file(self):
        """Create a temporary SSH key file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            # This is a dummy key for testing - not a real private key
            f.write("""-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAFwAAAAdzc2gtcn
NhAAAAAwEAAQAAAQEA1234567890abcdef...dummy...key...
-----END OPENSSH PRIVATE KEY-----""")
            temp_path = Path(f.name)
        
        yield str(temp_path)
        
        # Cleanup
        temp_path.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_ssh_config_with_key_file(self, temp_key_file):
        config = SSHConnectionConfig(
            hostname="test.com",
            username="test",
            private_key_path=temp_key_file,
        )
        
        assert config.private_key_path == temp_key_file
        assert Path(config.private_key_path).exists()
    
    @pytest.mark.asyncio 
    async def test_ssh_config_with_nonexistent_key(self):
        config = SSHConnectionConfig(
            hostname="test.com",
            username="test",
            private_key_path="/nonexistent/key.pem",
        )
        
        ssh_client = SSHClient()
        
        # This should raise an error when trying to create connection
        with pytest.raises((FileNotFoundError, ConnectionError)):
            async with ssh_client.connection(config) as conn:
                pass
    
    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self):
        """Test that connection pool properly reuses connections."""
        pool = SSHConnectionPool(max_connections=2)
        
        config = SSHConnectionConfig(
            hostname="test.com",
            username="test",
            password="dummy",  # Won't actually connect
        )
        
        # This test focuses on the pool logic rather than actual connections
        key = pool._get_connection_key(config)
        assert key == "test@test.com:22"
        
        await pool.close_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])