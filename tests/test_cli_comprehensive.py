"""
Comprehensive CLI tests for walNUT database commands.
"""
import os
from unittest.mock import patch, AsyncMock
import pytest
from walnut.cli.main import app
from walnut.database.engine import DatabaseError

@pytest.mark.usefixtures("mock_create_database_engine")
class TestDatabaseCLI:
    """Test database CLI commands using CliRunner."""

    def test_version_output(self, cli_runner):
        """Test version command displays correct information."""
        with patch('walnut.__version__', '1.2.3'):
            result = cli_runner.invoke(app, ["db", "version"])
            assert result.exit_code == 0
            assert "walNUT Database CLI" in result.output
            assert "Version: 1.2.3" in result.output

    @patch('walnut.cli.database.init_database')
    def test_init_command_success(self, mock_init, cli_runner):
        """Test init command execution path."""
        mock_init.return_value = {}
        result = cli_runner.invoke(app, ["db", "init", "--force"])
        assert "Database initialized successfully!" in result.output

    @patch('walnut.cli.database.init_database')
    def test_init_command_database_error(self, mock_init, cli_runner):
        """Test init command handles DatabaseError."""
        mock_init.side_effect = DatabaseError("Connection failed")
        result = cli_runner.invoke(app, ["db", "init"])
        assert "Database initialization failed: Connection failed" in result.output

    @patch('walnut.database.connection.get_db_session')
    @patch('walnut.cli.database.init_database')
    def test_stats_command_success(self, mock_init, mock_get_db_session, cli_runner, mock_db_session):
        """Test stats command execution."""
        mock_get_db_session.return_value = mock_db_session
        result = cli_runner.invoke(app, ["db", "stats"])
        assert "walNUT Database Information" in result.output

    @patch('click.confirm')
    @patch('walnut.database.connection.get_db_session')
    @patch('walnut.cli.database.init_database')
    def test_reset_command_confirmed(self, mock_init, mock_get_db_session, mock_confirm, cli_runner, mock_db_session):
        """Test reset command when confirmed."""
        mock_confirm.return_value = True
        mock_get_db_session.return_value = mock_db_session
        result = cli_runner.invoke(app, ["db", "reset", "--yes"])
        assert "Database reset successfully!" in result.output

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch('walnut.cli.database.get_master_key', return_value="a" * 32)
    @patch('walnut.cli.database.init_database')
    def test_test_encryption_command(self, mock_init, mock_get_key, cli_runner):
        """Test test-encryption command."""
        result = cli_runner.invoke(app, ["db", "test-encryption"])
        assert "Testing Encryption Setup" in result.output

    @patch('walnut.database.connection.get_db_session')
    @patch('walnut.cli.database.init_database')
    def test_vacuum_command_success(self, mock_init, mock_get_db_session, cli_runner, mock_db_session):
        """Test vacuum command execution."""
        mock_get_db_session.return_value = mock_db_session
        result = cli_runner.invoke(app, ["db", "vacuum"])
        assert "Database vacuumed successfully!" in result.output

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch('walnut.cli.database.init_database')
    @patch('walnut.cli.database.get_connection_manager')
    def test_backup_and_restore_commands(self, mock_get_conn_manager, mock_init, cli_runner):
        """Test backup and restore commands."""
        with cli_runner.isolated_filesystem():
            with open("test.db", "w") as f:
                f.write("test")

            mock_conn_manager = AsyncMock()
            mock_conn_manager.db_path = "test.db"
            mock_get_conn_manager.return_value = mock_conn_manager

            result = cli_runner.invoke(app, ["db", "backup", "--output", "backup.db"])
            assert "Database backed up successfully!" in result.output

            result = cli_runner.invoke(app, ["db", "restore", "--input", "backup.db"])
            assert "Database restored successfully!" in result.output

    def test_check_compatibility_command(self, cli_runner):
        """Test check-compatibility command."""
        result = cli_runner.invoke(app, ["db", "check-compatibility", "--target-version", "1.0.0"])
        assert "not yet implemented" in result.output

    def test_help_messages(self, cli_runner):
        """Test that all commands have help messages."""
        commands = ["init", "health", "stats", "reset", "test-encryption", "backup", "restore", "check-compatibility", "vacuum"]
        for command in commands:
            result = cli_runner.invoke(app, ["db", command, "--help"])
            assert result.exit_code == 0
            assert f"Usage: {app.name} db {command}" in result.output
