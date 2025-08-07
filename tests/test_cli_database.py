"""
Comprehensive tests for walNUT database CLI commands.

Tests all CLI commands, error handling, edge cases, and user interactions
to achieve 100% coverage of walnut/cli/database.py.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from typer.testing import CliRunner
from rich.console import Console

from walnut.cli import database
from walnut.cli.database import handle_async_command
from walnut.database.engine import DatabaseError


class TestCLICommandDecorator:
    """Test the handle_async_command decorator."""
    
    def test_handle_async_command_success(self):
        """Test decorator with successful async function."""
        @handle_async_command
        async def test_func(arg1, arg2=None):
            return f"success: {arg1}, {arg2}"
        
        result = test_func("value1", arg2="value2")
        assert result == "success: value1, value2"
    
    def test_handle_async_command_keyboard_interrupt(self):
        """Test decorator handling KeyboardInterrupt."""
        @handle_async_command  
        async def test_func():
            raise KeyboardInterrupt()
        
        with patch('sys.exit') as mock_exit:
            with patch('walnut.cli.database.console.print') as mock_print:
                test_func()
                mock_print.assert_called_with("\n[yellow]Operation cancelled by user[/yellow]")
                mock_exit.assert_called_with(1)
    
    def test_handle_async_command_general_exception(self):
        """Test decorator handling general exceptions."""
        @handle_async_command
        async def test_func():
            raise ValueError("Test error")
        
        with patch('sys.exit') as mock_exit:
            with patch('walnut.cli.database.console.print') as mock_print:
                test_func()
                mock_print.assert_called_with("[red]Error: Test error[/red]")
                mock_exit.assert_called_with(1)


class TestInitCommand:
    """Test the init CLI command."""
    
    def setup_method(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = Path(self.temp_dir) / "test.db"
    
    def teardown_method(self):
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    async def test_init_success_default_path(self, mock_close, mock_init):
        """Test successful initialization with default path."""
        mock_init.return_value = {
            "connection_test": True,
            "encryption_enabled": True,
            "wal_mode_enabled": True,
            "database_url_type": "sqlite+async_sqlcipher"
        }
        
        # Test the actual async function directly
        from walnut.cli import database
        await database.init.__wrapped__(db_path=None, force=False, echo=False)
        
        mock_init.assert_called_once_with(
            db_path=None,
            echo=False,
            create_tables=True
        )
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    async def test_init_success_custom_path(self, mock_close, mock_init):
        """Test successful initialization with custom path."""
        mock_init.return_value = {
            "connection_test": True,
            "encryption_enabled": True
        }
        
        from walnut.cli import database
        await database.init.__wrapped__(db_path=str(self.temp_db), force=False, echo=True)
        
        mock_init.assert_called_once_with(
            db_path=str(self.temp_db),
            echo=True,
            create_tables=True
        )
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.console.print')
    async def test_init_existing_database_no_force(self, mock_print):
        """Test initialization when database exists without force."""
        # Create existing database file
        self.temp_db.touch()
        
        from walnut.cli import database
        await database.init.__wrapped__(db_path=str(self.temp_db), force=False, echo=False)
        
        mock_print.assert_any_call(f"[yellow]Database already exists at {self.temp_db}[/yellow]")
        mock_print.assert_any_call("Use --force to reinitialize")
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    async def test_init_existing_database_with_force(self, mock_close, mock_init):
        """Test initialization when database exists with force."""
        # Create existing database file
        self.temp_db.touch()
        mock_init.return_value = {"connection_test": True}
        
        from walnut.cli import database
        await database.init.__wrapped__(db_path=str(self.temp_db), force=True, echo=False)
        
        mock_init.assert_called_once()
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_init_database_error(self, mock_print, mock_close, mock_init):
        """Test initialization when database error occurs."""
        mock_init.side_effect = DatabaseError("Connection failed")
        
        from walnut.cli import database
        await database.init.__wrapped__(db_path=str(self.temp_db), force=False, echo=False)
        
        mock_print.assert_any_call("[red]Database initialization failed: Connection failed[/red]")
        mock_close.assert_called_once()
    
    async def test_init_diagnostics_formatting(self):
        """Test that diagnostics are formatted correctly."""
        with patch('walnut.cli.database.init_database') as mock_init:
            with patch('walnut.cli.database.close_database'):
                with patch('walnut.cli.database.console.print') as mock_print:
                    mock_init.return_value = {
                        "connection_test": True,
                        "encryption_enabled": False,
                        "database_url_type": None,
                        "custom_field": "test_value"
                    }
                    
                    from walnut.cli import database
                    await init(db_path=str(self.temp_db), force=False, echo=False)
                    
                    # Check that table formatting was called with diagnostics
                    mock_print.assert_any_call("\n[green]✅ Database initialized successfully![/green]")


class TestHealthCommand:
    """Test the health CLI command."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = Path(self.temp_dir) / "test.db"
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    async def test_health_success_table_output(self, mock_close, mock_get_manager, mock_init):
        """Test health command with successful table output."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {
                "connection_test": True,
                "encryption_enabled": True,
                "wal_mode_enabled": False,
                "cipher_version": None
            },
            "pool_status": {
                "active_connections": 2,
                "pool_size": 5,
                "checked_out": 1
            }
        }
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await health(db_path=str(self.temp_db), json_output=False)
        
        mock_init.assert_called_once_with(db_path=str(self.temp_db), create_tables=False)
        mock_manager.health_check.assert_called_once()
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_health_success_json_output(self, mock_print, mock_close, mock_get_manager, mock_init):
        """Test health command with JSON output."""
        health_data = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": True}
        }
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = health_data
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await health(db_path=None, json_output=True)
        
        # Check that JSON was printed
        mock_print.assert_called()
        print_call = mock_print.call_args[0][0]
        assert hasattr(print_call, 'json')  # Rich JSON object
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_health_unhealthy_database(self, mock_print, mock_close, mock_get_manager, mock_init):
        """Test health command when database is unhealthy."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": False,
            "error": "Connection timeout"
        }
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await health(db_path=None, json_output=False)
        
        mock_print.assert_any_call("[red]❌ Database health check failed[/red]")
        mock_print.assert_any_call("[red]Error: Connection timeout[/red]")
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('sys.exit')
    async def test_health_exception_table_output(self, mock_exit, mock_close, mock_init):
        """Test health command when exception occurs with table output."""
        mock_init.side_effect = Exception("Database not found")
        
        with patch('walnut.cli.database.console.print') as mock_print:
            from walnut.cli import database
            await health(db_path=None, json_output=False)
            
            mock_print.assert_any_call("[red]Health check failed: Database not found[/red]")
            mock_exit.assert_called_with(1)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('sys.exit')
    async def test_health_exception_json_output(self, mock_exit, mock_close, mock_init):
        """Test health command when exception occurs with JSON output."""
        mock_init.side_effect = Exception("Database not found")
        
        with patch('walnut.cli.database.console.print') as mock_print:
            from walnut.cli import database
            await health(db_path=None, json_output=True)
            
            # Should print JSON error response
            mock_print.assert_called()
            mock_exit.assert_called_with(1)


class TestInfoCommand:
    """Test the info CLI command."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = Path(self.temp_dir) / "test.db"
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Base')
    async def test_info_success(self, mock_base, mock_close, mock_get_manager, mock_init):
        """Test successful info command."""
        # Mock metadata tables
        mock_base.metadata.tables.keys.return_value = ['ups_samples', 'events', 'hosts']
        
        # Mock session and database queries
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Mock query results
        def mock_execute(query):
            query_str = str(query)
            result = MagicMock()
            if "COUNT(*)" in query_str:
                if "ups_samples" in query_str:
                    result.scalar.return_value = 100
                elif "events" in query_str:
                    result.scalar.return_value = 50
                else:
                    result.scalar.return_value = 25
            elif "PRAGMA page_count" in query_str:
                result.scalar.return_value = 1000
            elif "PRAGMA page_size" in query_str:
                result.scalar.return_value = 4096
            elif "PRAGMA journal_mode" in query_str:
                result.scalar.return_value = "wal"
            elif "PRAGMA synchronous" in query_str:
                result.scalar.return_value = 1
            elif "PRAGMA cache_size" in query_str:
                result.scalar.return_value = -2000
            elif "PRAGMA foreign_keys" in query_str:
                result.scalar.return_value = 1
            else:
                result.scalar.return_value = "unknown"
            return result
        
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        
        from walnut.cli import database
        await info(db_path=str(self.temp_db))
        
        mock_init.assert_called_once_with(db_path=str(self.temp_db), create_tables=False)
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Base')
    async def test_info_table_query_error(self, mock_base, mock_close, mock_get_manager, mock_init):
        """Test info command when table queries fail."""
        mock_base.metadata.tables.keys.return_value = ['test_table']
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Make table count query fail
        mock_session.execute.side_effect = Exception("Table not found")
        
        from walnut.cli import database
        await info(db_path=None)
        
        # Should handle the error gracefully and still complete
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('sys.exit')
    async def test_info_init_failure(self, mock_exit, mock_close, mock_init):
        """Test info command when database initialization fails."""
        mock_init.side_effect = Exception("Cannot connect to database")
        
        with patch('walnut.cli.database.console.print') as mock_print:
            from walnut.cli import database
            await info(db_path=None)
            
            mock_print.assert_any_call("[red]Failed to get database info: Cannot connect to database[/red]")
            mock_exit.assert_called_with(1)


class TestResetCommand:
    """Test the reset CLI command."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = Path(self.temp_dir) / "test.db"
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    async def test_reset_success_with_confirm(self, mock_close, mock_get_manager, mock_init):
        """Test successful reset with confirmation."""
        mock_manager = AsyncMock()
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await reset(db_path=str(self.temp_db), confirm=True)
        
        mock_init.assert_called_once_with(db_path=str(self.temp_db), create_tables=False)
        mock_manager.drop_tables.assert_called_once()
        mock_manager.create_tables.assert_called_once()
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.console.print')
    @patch('typer.confirm')
    async def test_reset_cancelled_by_user(self, mock_confirm, mock_print):
        """Test reset cancelled by user."""
        mock_confirm.return_value = False
        
        from walnut.cli import database
        await reset(db_path=None, confirm=False)
        
        mock_print.assert_any_call("[red]⚠️  WARNING: This will delete ALL database data![/red]")
        mock_print.assert_any_call("Operation cancelled")
        mock_confirm.assert_called_once_with("Are you sure you want to continue?")
    
    @patch('typer.confirm')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    async def test_reset_confirmed_by_user(self, mock_close, mock_get_manager, mock_init, mock_confirm):
        """Test reset confirmed by user prompt."""
        mock_confirm.return_value = True
        mock_manager = AsyncMock()
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await reset(db_path=None, confirm=False)
        
        mock_confirm.assert_called_once()
        mock_manager.drop_tables.assert_called_once()
        mock_manager.create_tables.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('sys.exit')
    async def test_reset_failure(self, mock_exit, mock_close, mock_init):
        """Test reset when operation fails."""
        mock_init.side_effect = Exception("Database locked")
        
        with patch('walnut.cli.database.console.print') as mock_print:
            from walnut.cli import database
            await reset(db_path=None, confirm=True)
            
            mock_print.assert_any_call("[red]Database reset failed: Database locked[/red]")
            mock_exit.assert_called_with(1)


class TestEncryptionTestCommand:
    """Test the test-encryption CLI command."""
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_master_key_success(self, mock_print, mock_get_key):
        """Test encryption test with successful master key."""
        mock_get_key.return_value = "a_very_long_secure_master_key_32_chars"
        
        with patch('walnut.cli.database.init_database') as mock_init:
            with patch('walnut.cli.database.get_connection_manager') as mock_get_manager:
                with patch('walnut.cli.database.close_database'):
                    # Setup mock health check response
                    mock_manager = AsyncMock()
                    mock_manager.health_check.return_value = {
                        "healthy": True,
                        "engine_diagnostics": {
                            "encryption_enabled": True,
                            "cipher_version": "4.5.0"
                        }
                    }
                    mock_get_manager.return_value = mock_manager
                    
                    from walnut.cli import database
                    await test_encryption()
                    
                    mock_print.assert_any_call("[green]✅ Master key loaded successfully[/green]")
                    mock_print.assert_any_call("[green]✅ Key length meets security requirements[/green]")
                    mock_print.assert_any_call("[green]✅ Database encryption is working[/green]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_short_key_warning(self, mock_print, mock_get_key):
        """Test encryption test with short key warning."""
        mock_get_key.return_value = "short_key"
        
        from walnut.cli import database
        await test_encryption()
        
        mock_print.assert_any_call("[green]✅ Master key loaded successfully[/green]")
        mock_print.assert_any_call("[red]⚠️  WARNING: Key is shorter than recommended 32 characters[/red]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_master_key_failure(self, mock_print, mock_get_key):
        """Test encryption test when master key fails."""
        mock_get_key.side_effect = Exception("Key not found")
        
        from walnut.cli import database
        await test_encryption()
        
        mock_print.assert_any_call("[red]❌ Master key test failed: Key not found[/red]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_database_unhealthy(self, mock_print, mock_close, mock_get_manager, mock_init, mock_get_key):
        """Test encryption test when database is unhealthy."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {"healthy": False}
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await test_encryption()
        
        mock_print.assert_any_call("[red]❌ Database health check failed[/red]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_no_encryption(self, mock_print, mock_close, mock_get_manager, mock_init, mock_get_key):
        """Test encryption test when encryption not detected."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": False}
        }
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await test_encryption()
        
        mock_print.assert_any_call("[red]❌ Database encryption not detected[/red]")
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.console.print')
    async def test_encryption_test_database_exception(self, mock_print, mock_close, mock_init, mock_get_key):
        """Test encryption test when database operations fail."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        mock_init.side_effect = Exception("Database connection failed")
        
        from walnut.cli import database
        await test_encryption()
        
        mock_print.assert_any_call("[red]❌ Encryption test failed: Database connection failed[/red]")
        mock_close.assert_called()
    
    @patch('walnut.cli.database.get_master_key')
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Path')
    async def test_encryption_test_cleanup(self, mock_path, mock_close, mock_get_manager, mock_init, mock_get_key):
        """Test that test database file is cleaned up."""
        mock_get_key.return_value = "secure_key_32_characters_long_123"
        
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {
            "healthy": True,
            "engine_diagnostics": {"encryption_enabled": True}
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock Path for cleanup
        mock_db_file = MagicMock()
        mock_db_file.exists.return_value = True
        mock_path.return_value = mock_db_file
        
        from walnut.cli import database
        await test_encryption()
        
        mock_db_file.unlink.assert_called_once()


class TestVersionCommand:
    """Test the version CLI command."""
    
    @patch('walnut.cli.database.console.print')
    def test_version_display(self, mock_print):
        """Test version command displays correct information."""
        with patch('walnut.__version__', '1.2.3'):
            from walnut.cli import database
            version()
            
            mock_print.assert_any_call("[bold blue]walNUT Database CLI[/bold blue]")
            mock_print.assert_any_call("Version: 1.2.3")
            mock_print.assert_any_call("SQLCipher-based encrypted SQLite storage")


class TestCLIIntegration:
    """Integration tests for CLI commands using CliRunner."""
    
    def setup_method(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_version_command_integration(self):
        """Test version command through CLI runner."""
        result = self.runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "walNUT Database CLI" in result.stdout
        assert "SQLCipher-based encrypted SQLite storage" in result.stdout
    
    @patch.dict(os.environ, {'WALNUT_DB_KEY': 'test_key_32_characters_minimum_length'})
    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "walNUT Database Management Commands" in result.stdout
        
        # Check that all commands are listed
        assert "init" in result.stdout
        assert "health" in result.stdout
        assert "info" in result.stdout
        assert "reset" in result.stdout
        assert "test-encryption" in result.stdout
        assert "version" in result.stdout
    
    def test_command_help_messages(self):
        """Test individual command help messages."""
        commands = ["init", "health", "info", "reset", "test-encryption"]
        
        for command in commands:
            result = self.runner.invoke(app, [command, "--help"])
            assert result.exit_code == 0, f"Help for {command} failed"
            assert command in result.stdout or command.replace("-", "_") in result.stdout


# Additional edge case tests for missed lines
class TestEdgeCases:
    """Test edge cases and error conditions for complete coverage."""
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.close_database')
    async def test_init_with_none_values_in_diagnostics(self, mock_close, mock_init):
        """Test init command handling None values in diagnostics."""
        mock_init.return_value = {
            "connection_test": None,
            "encryption_enabled": True,
            "database_url_type": None
        }
        
        with patch('walnut.cli.database.console.print'):
            from walnut.cli import database
            await init(db_path=None, force=False, echo=False)
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    async def test_health_command_missing_diagnostics(self, mock_close, mock_get_manager, mock_init):
        """Test health command when diagnostics sections are missing."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {"healthy": True}  # No engine_diagnostics or pool_status
        mock_get_manager.return_value = mock_manager
        
        from walnut.cli import database
        await health(db_path=None, json_output=False)
        
        mock_manager.health_check.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Base')
    async def test_info_command_no_tables(self, mock_base, mock_close, mock_get_manager, mock_init):
        """Test info command when no tables exist."""
        mock_base.metadata.tables.keys.return_value = []
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Mock PRAGMA queries
        def mock_execute(query):
            result = MagicMock()
            result.scalar.return_value = "test_value"
            return result
        
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        
        from walnut.cli import database
        await info(db_path=None)
        
        mock_close.assert_called_once()
    
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.Base')
    async def test_info_command_pragma_failures(self, mock_base, mock_close, mock_get_manager, mock_init):
        """Test info command when PRAGMA queries fail."""
        mock_base.metadata.tables.keys.return_value = []
        
        mock_session = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_session.return_value.__aenter__.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        # Make all PRAGMA queries fail
        mock_session.execute = AsyncMock(side_effect=Exception("PRAGMA failed"))
        
        from walnut.cli import database
        await info(db_path=None)
        
        mock_close.assert_called_once()