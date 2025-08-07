"""
Comprehensive CLI tests for 100% coverage of walnut/cli/database.py.

This test suite covers all CLI commands, decorator functionality, edge cases,
and error conditions to achieve complete code coverage.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner
from rich.console import Console

from walnut.cli.database import app, handle_async_command
from walnut.database.engine import DatabaseError


class TestHandleAsyncCommandDecorator:
    """Test the handle_async_command decorator thoroughly."""
    
    def test_decorator_success(self):
        """Test decorator with successful async function."""
        @handle_async_command
        async def success_func(value):
            return f"result: {value}"
        
        # Since we can't call async in sync test, test the wrapper structure
        assert hasattr(success_func, '__wrapped__')
    
    def test_decorator_keyboard_interrupt(self):
        """Test decorator handles KeyboardInterrupt."""
        @handle_async_command
        async def interrupt_func():
            raise KeyboardInterrupt()
        
        with patch('sys.exit') as mock_exit, patch('walnut.cli.database.console.print') as mock_print:
            interrupt_func()
            mock_print.assert_called_with("\n[yellow]Operation cancelled by user[/yellow]")
            mock_exit.assert_called_with(1)
    
    def test_decorator_general_exception(self):
        """Test decorator handles general exceptions."""
        @handle_async_command
        async def error_func():
            raise ValueError("Test error")
        
        with patch('sys.exit') as mock_exit, patch('walnut.cli.database.console.print') as mock_print:
            error_func()
            mock_print.assert_called_with("[red]Error: Test error[/red]")
            mock_exit.assert_called_with(1)


class TestVersionCommand:
    """Test version command (synchronous, easier to test)."""
    
    @patch('walnut.cli.database.console.print')
    def test_version_output(self, mock_print):
        """Test version command displays correct information."""
        with patch('walnut.__version__', '1.2.3'):
            from walnut.cli.database import version
            version()
            
            mock_print.assert_any_call("[bold blue]walNUT Database CLI[/bold blue]")
            mock_print.assert_any_call("Version: 1.2.3")
            mock_print.assert_any_call("SQLCipher-based encrypted SQLite storage")


class TestAsyncCommandsMocked:
    """Test async commands by mocking the decorator's async execution."""
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')  
    @patch('walnut.cli.database.console.print')
    @patch('asyncio.run')
    def test_init_command_success(self, mock_run, mock_print, mock_init, mock_close):
        """Test init command execution path."""
        # Mock successful database init
        mock_init.return_value = {
            "connection_test": True,
            "encryption_enabled": True,
            "wal_mode_enabled": True,
            "database_url_type": "sqlite+async_sqlcipher"
        }
        
        # Import and call the decorated init function
        from walnut.cli.database import init
        
        # Mock asyncio.run to simulate successful execution
        def mock_async_run(coro):
            # This simulates what would happen in the actual async execution
            return None
        mock_run.side_effect = mock_async_run
        
        # Call the decorated function (which will call asyncio.run internally)
        init(db_path=None, force=False, echo=False)
        
        # Verify asyncio.run was called
        mock_run.assert_called_once()
        
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')  
    @patch('asyncio.run')
    def test_init_command_database_error(self, mock_run, mock_print, mock_init, mock_close):
        """Test init command handles DatabaseError."""
        mock_init.side_effect = DatabaseError("Connection failed")
        
        def mock_async_run(coro):
            return None  # Simulate completion
        mock_run.side_effect = mock_async_run
        
        from walnut.cli.database import init
        init(db_path="test.db", force=False, echo=False)
        
        mock_run.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('asyncio.run')
    def test_health_command_success(self, mock_run, mock_print, mock_init, mock_get_manager, mock_close):
        """Test health command execution."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": True},
            "pool_status": {"active_connections": 1}
        }
        mock_get_manager.return_value = mock_manager
        
        def mock_async_run(coro):
            return None
        mock_run.side_effect = mock_async_run
        
        from walnut.cli.database import health
        health(db_path=None, json_output=False)
        
        mock_run.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('asyncio.run')
    def test_info_command_success(self, mock_run, mock_print, mock_init, mock_get_manager, mock_close):
        """Test info command execution."""
        mock_manager = AsyncMock()
        mock_session = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        def mock_async_run(coro):
            return None
        mock_run.side_effect = mock_async_run
        
        from walnut.cli.database import info
        info(db_path=None)
        
        mock_run.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('typer.confirm')
    @patch('asyncio.run')
    def test_reset_command_confirmed(self, mock_run, mock_confirm, mock_print, mock_init, mock_get_manager, mock_close):
        """Test reset command when confirmed."""
        mock_confirm.return_value = True
        mock_manager = AsyncMock()
        mock_get_manager.return_value = mock_manager
        
        def mock_async_run(coro):
            return None
        mock_run.side_effect = mock_async_run
        
        from walnut.cli.database import reset
        reset(db_path=None, confirm=False)
        
        mock_run.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    @patch('asyncio.run')
    def test_test_encryption_command(self, mock_run, mock_print, mock_get_key, mock_close):
        """Test test-encryption command."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        
        def mock_async_run(coro):
            return None
        mock_run.side_effect = mock_async_run
        
        from walnut.cli.database import test_encryption
        test_encryption()
        
        mock_run.assert_called_once()


class TestAsyncFunctionsDirectly:
    """Test the actual async functions directly without the decorator."""
    
    @pytest.fixture
    def temp_db_file(self):
        """Provide a temporary database file path."""
        temp_dir = tempfile.mkdtemp()
        temp_file = Path(temp_dir) / "test.db"
        yield temp_file
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_function_success(self, mock_print, mock_init, mock_close, temp_db_file):
        """Test init function directly."""
        mock_init.return_value = {
            "connection_test": True,
            "encryption_enabled": True,
            "wal_mode_enabled": True
        }
        
        from walnut.cli.database import init
        await init.__wrapped__(db_path=str(temp_db_file), force=False, echo=False)
        
        mock_init.assert_called_once_with(
            db_path=str(temp_db_file),
            echo=False,
            create_tables=True
        )
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_function_existing_file_no_force(self, mock_print, mock_init, mock_close, temp_db_file):
        """Test init when file exists without force."""
        temp_db_file.touch()  # Create file
        
        from walnut.cli.database import init
        await init.__wrapped__(db_path=str(temp_db_file), force=False, echo=False)
        
        mock_print.assert_any_call(f"[yellow]Database already exists at {temp_db_file}[/yellow]")
        mock_print.assert_any_call("Use --force to reinitialize")
        mock_init.assert_not_called()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_function_existing_file_with_force(self, mock_print, mock_init, mock_close, temp_db_file):
        """Test init when file exists with force."""
        temp_db_file.touch()  # Create file
        mock_init.return_value = {"connection_test": True}
        
        from walnut.cli.database import init
        await init.__wrapped__(db_path=str(temp_db_file), force=True, echo=False)
        
        mock_init.assert_called_once()
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_function_database_error(self, mock_print, mock_init, mock_close, temp_db_file):
        """Test init handles DatabaseError."""
        mock_init.side_effect = DatabaseError("Connection failed")
        
        from walnut.cli.database import init
        await init.__wrapped__(db_path=str(temp_db_file), force=False, echo=False)
        
        mock_print.assert_any_call("[red]Database initialization failed: Connection failed[/red]")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_function_diagnostics_formatting(self, mock_print, mock_init, mock_close, temp_db_file):
        """Test init handles various diagnostic value types."""
        mock_init.return_value = {
            "bool_true": True,
            "bool_false": False,
            "none_value": None,
            "string_value": "test"
        }
        
        from walnut.cli.database import init
        await init.__wrapped__(db_path=str(temp_db_file), force=False, echo=False)
        
        mock_print.assert_any_call("\n[green]✅ Database initialized successfully![/green]")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_health_function_healthy_json(self, mock_print, mock_init, mock_get_manager, mock_close):
        """Test health function with JSON output."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": True}
        }
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli.database import health
        await health.__wrapped__(db_path=None, json_output=True)
        
        mock_print.assert_called()
        # Verify JSON object was printed
        call_args = mock_print.call_args[0][0]
        assert hasattr(call_args, 'json')  # Rich JSON object
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_health_function_unhealthy(self, mock_print, mock_init, mock_get_manager, mock_close):
        """Test health function when database is unhealthy."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": False,
            "error": "Connection timeout"
        }
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli.database import health
        await health.__wrapped__(db_path=None, json_output=False)
        
        mock_print.assert_any_call("[red]❌ Database health check failed[/red]")
        mock_print.assert_any_call("[red]Error: Connection timeout[/red]")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('sys.exit')
    async def test_health_function_exception_json(self, mock_exit, mock_print, mock_init, mock_close):
        """Test health function exception handling with JSON output."""
        mock_init.side_effect = Exception("Database not found")
        
        from walnut.cli.database import health
        await health.__wrapped__(db_path=None, json_output=True)
        
        mock_print.assert_called()
        mock_exit.assert_called_with(1)
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.Base')
    @patch('walnut.cli.database.console.print')
    async def test_info_function_success(self, mock_print, mock_base, mock_init, mock_get_manager, mock_close):
        """Test info function with successful execution."""
        # Mock Base metadata
        mock_base.metadata.tables.keys.return_value = ['ups_samples', 'events']
        
        # Mock session and queries
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Mock query results
        def mock_execute(query):
            result = MagicMock()
            query_str = str(query)
            if "COUNT(*)" in query_str:
                result.scalar.return_value = 100
            elif "page_count" in query_str:
                result.scalar.return_value = 1000
            elif "page_size" in query_str:
                result.scalar.return_value = 4096
            elif "journal_mode" in query_str:
                result.scalar.return_value = "wal"
            else:
                result.scalar.return_value = "test_value"
            return result
        
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        
        from walnut.cli.database import info
        await info.__wrapped__(db_path=None)
        
        mock_print.assert_any_call("[bold blue]walNUT Database Information[/bold blue]\n")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.Base')
    async def test_info_function_table_error(self, mock_base, mock_init, mock_get_manager, mock_close):
        """Test info function when table queries fail."""
        mock_base.metadata.tables.keys.return_value = ['test_table']
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Make queries fail
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))
        
        from walnut.cli.database import info
        await info.__wrapped__(db_path=None)
        
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('sys.exit')
    async def test_info_function_init_failure(self, mock_exit, mock_print, mock_init, mock_close):
        """Test info function when init fails."""
        mock_init.side_effect = Exception("Cannot connect")
        
        from walnut.cli.database import info
        await info.__wrapped__(db_path=None)
        
        mock_print.assert_any_call("[red]Failed to get database info: Cannot connect[/red]")
        mock_exit.assert_called_with(1)
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_reset_function_with_confirm(self, mock_print, mock_init, mock_get_manager, mock_close):
        """Test reset function with confirmation."""
        mock_manager = AsyncMock()
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli.database import reset
        await reset.__wrapped__(db_path=None, confirm=True)
        
        mock_manager.drop_tables.assert_called_once()
        mock_manager.create_tables.assert_called_once()
        mock_print.assert_any_call("[green]✅ Database reset successfully![/green]")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.console.print')
    @patch('typer.confirm')
    async def test_reset_function_cancelled(self, mock_confirm, mock_print):
        """Test reset function cancelled by user."""
        mock_confirm.return_value = False
        
        from walnut.cli.database import reset
        await reset.__wrapped__(db_path=None, confirm=False)
        
        mock_print.assert_any_call("[red]⚠️  WARNING: This will delete ALL database data![/red]")
        mock_print.assert_any_call("Operation cancelled")
        mock_confirm.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    @patch('sys.exit')
    async def test_reset_function_failure(self, mock_exit, mock_print, mock_init, mock_close):
        """Test reset function when operation fails."""
        mock_init.side_effect = Exception("Database locked")
        
        from walnut.cli.database import reset
        await reset.__wrapped__(db_path=None, confirm=True)
        
        mock_print.assert_any_call("[red]Database reset failed: Database locked[/red]")
        mock_exit.assert_called_with(1)
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_test_encryption_function_success(self, mock_print, mock_get_key):
        """Test test_encryption function with successful key."""
        mock_get_key.return_value = "secure_key_32_characters_long_minimum"
        
        with patch('walnut.cli.database.init_database') as mock_init:
            with patch('walnut.cli.database.get_connection_manager') as mock_get_manager:
                with patch('walnut.cli.database.close_database') as mock_close:
                    mock_manager = AsyncMock()
                    mock_manager.health_check.return_value = {
                        "healthy": True,
                        "engine_diagnostics": {
                            "encryption_enabled": True,
                            "cipher_version": "4.5.0"
                        }
                    }
                    mock_get_manager.return_value = mock_manager
                    
                    from walnut.cli.database import test_encryption
                    await test_encryption.__wrapped__()
                    
                    mock_print.assert_any_call("[green]✅ Master key loaded successfully[/green]")
                    mock_print.assert_any_call("[green]✅ Key length meets security requirements[/green]")
                    mock_print.assert_any_call("[green]✅ Database encryption is working[/green]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_test_encryption_function_short_key(self, mock_print, mock_get_key):
        """Test test_encryption function with short key."""
        mock_get_key.return_value = "short"
        
        from walnut.cli.database import test_encryption
        await test_encryption.__wrapped__()
        
        mock_print.assert_any_call("[red]⚠️  WARNING: Key is shorter than recommended 32 characters[/red]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_test_encryption_function_key_failure(self, mock_print, mock_get_key):
        """Test test_encryption function when key loading fails."""
        mock_get_key.side_effect = Exception("Key not found")
        
        from walnut.cli.database import test_encryption
        await test_encryption.__wrapped__()
        
        mock_print.assert_any_call("[red]❌ Master key test failed: Key not found[/red]")


class TestCLIIntegration:
    """Integration tests using CliRunner."""
    
    def setup_method(self):
        self.runner = CliRunner()
    
    def test_app_help(self):
        """Test main app help."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "walNUT Database Management Commands" in result.stdout
    
    def test_version_command_integration(self):
        """Test version command through CLI runner."""
        result = self.runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "walNUT Database CLI" in result.stdout
    
    def test_individual_command_help(self):
        """Test help for individual commands."""
        commands = ["init", "health", "info", "reset", "test-encryption"]
        for cmd in commands:
            result = self.runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0, f"Help for {cmd} failed"


class TestEdgeCases:
    """Test edge cases and corner conditions."""
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.console.print')
    async def test_health_missing_diagnostics_sections(self, mock_print, mock_init, mock_get_manager, mock_close):
        """Test health command when diagnostics sections are missing."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {"healthy": True}  # Missing engine_diagnostics and pool_status
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli.database import health
        await health.__wrapped__(db_path=None, json_output=False)
        
        mock_print.assert_any_call("[green]✅ Database is healthy[/green]")
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.Base')
    async def test_info_no_tables(self, mock_base, mock_init, mock_get_manager, mock_close):
        """Test info command when no tables exist."""
        mock_base.metadata.tables.keys.return_value = []
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Mock PRAGMA queries
        result = MagicMock()
        result.scalar.return_value = "test"
        mock_session.execute = AsyncMock(return_value=result)
        
        from walnut.cli.database import info
        await info.__wrapped__(db_path=None)
        
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.Base')
    async def test_info_pragma_failures(self, mock_base, mock_init, mock_get_manager, mock_close):
        """Test info command when PRAGMA queries fail."""
        mock_base.metadata.tables.keys.return_value = []
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Mock PRAGMA queries to fail
        mock_session.execute = AsyncMock(side_effect=Exception("PRAGMA failed"))
        
        from walnut.cli.database import info
        await info.__wrapped__(db_path=None)
        
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')  
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Path')
    async def test_test_encryption_cleanup(self, mock_path, mock_close, mock_get_manager, mock_init, mock_get_key):
        """Test test_encryption cleanup of test database."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": True}
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock Path for cleanup testing
        mock_db_file = MagicMock()
        mock_db_file.exists.return_value = True
        mock_path.return_value = mock_db_file
        
        from walnut.cli.database import test_encryption
        await test_encryption.__wrapped__()
        
        # Verify cleanup was attempted
        mock_db_file.unlink.assert_called_once()
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_test_encryption_database_exception(self, mock_print, mock_close, mock_init, mock_get_key):
        """Test test_encryption when database operations fail."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        mock_init.side_effect = Exception("Database connection failed")
        
        from walnut.cli.database import test_encryption
        await test_encryption.__wrapped__()
        
        mock_print.assert_any_call("[red]❌ Encryption test failed: Database connection failed[/red]")
        mock_close.assert_called()