"""
Comprehensive CLI tests for walNUT database commands.
"""

import os
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from walnut.cli.main import app
from walnut.database.engine import DatabaseError
from contextlib import asynccontextmanager


class TestDatabaseCLI:
    """Test database CLI commands using CliRunner."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_version_output(self):
        """Test version command displays correct information."""
        with patch('walnut.__version__', '1.2.3'):
            result = self.runner.invoke(app, ["db", "version"])
            assert result.exit_code == 0
            assert "walNUT Database CLI" in result.output
            assert "Version: 1.2.3" in result.output

    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    def test_init_command_success(self, mock_init, mock_close):
        """Test init command execution path."""
        mock_init.return_value = {
            "connection_test": True,
            "encryption_enabled": True,
        }
        result = self.runner.invoke(app, ["db", "init"])
        assert result.exit_code == 0

    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.init_database')
    def test_init_command_database_error(self, mock_init, mock_close):
        """Test init command handles DatabaseError."""
        mock_init.side_effect = DatabaseError("Connection failed")
        result = self.runner.invoke(app, ["db", "init"])
        assert "Database initialization failed: Connection failed" in result.output

    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    def test_health_command_success(self, mock_init, mock_get_manager, mock_close):
        """Test health command execution."""
        mock_manager = AsyncMock()
        mock_manager.health_check.return_value = {"healthy": True}
        mock_get_manager.return_value = mock_manager
        result = self.runner.invoke(app, ["db", "health"])
        assert result.exit_code == 0

    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    def test_info_command_success(self, mock_init, mock_get_manager, mock_close):
        """Test info command execution."""
        mock_manager = AsyncMock()
        mock_session = AsyncMock()

        @asynccontextmanager
        async def get_session_mock():
            yield mock_session

        mock_manager.get_session = get_session_mock
        mock_get_manager.return_value = mock_manager
        result = self.runner.invoke(app, ["db", "info"])
        assert result.exit_code == 0

    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_connection_manager')
    @patch('walnut.cli.database.init_database')
    @patch('click.confirm')
    def test_reset_command_confirmed(self, mock_confirm, mock_init, mock_get_manager, mock_close):
        """Test reset command when confirmed."""
        mock_confirm.return_value = True
        result = self.runner.invoke(app, ["db", "reset", "--yes"])
        assert result.exit_code == 0

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch('walnut.cli.database.close_database')
    @patch('walnut.cli.database.get_master_key', return_value="a" * 32)
    @patch('walnut.cli.database.init_database')
    def test_test_encryption_command(self, mock_init, mock_get_key, mock_close):
        """Test test-encryption command."""
        result = self.runner.invoke(app, ["db", "test-encryption"])
        assert result.exit_code == 0

    def test_help_messages(self):
        """Test that all commands have help messages."""
        commands = ["init", "health", "info", "reset", "test-encryption", "backup", "restore", "check-compatibility", "vacuum", "stats"]
        for command in commands:
            result = self.runner.invoke(app, ["db", command, "--help"])
            assert result.exit_code == 0
            assert f"Usage: {app.name} db {command}" in result.output
