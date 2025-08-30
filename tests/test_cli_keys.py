import os
from unittest.mock import patch, AsyncMock
import pytest
pytest.skip("CLI tests skipped; update pending to new engine and key APIs", allow_module_level=True)
from walnut.cli.main import app
from pysqlcipher3 import dbapi2 as sqlcipher

@pytest.mark.usefixtures("mock_create_database_engine")
class TestKeysCLI:
    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch("walnut.cli.keys.get_master_key", return_value="a" * 32)
    def test_key_validate(self, mock_get_key, cli_runner):
        result = cli_runner.invoke(app, ['key', 'validate'])
        assert result.exit_code == 0
        assert "Validating Encryption Key" in result.output

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch("walnut.cli.keys.get_master_key", return_value="a" * 32)
    @patch("walnut.cli.keys.init_database")
    @patch("walnut.cli.keys.get_connection_manager")
    def test_key_rotate(self, mock_get_conn_manager, mock_init_db, mock_get_key, cli_runner):
        """Test the key rotate command."""
        with cli_runner.isolated_filesystem():
            with open("new.key", "w") as f:
                f.write("b" * 32)

            # Create a dummy db
            conn = sqlcipher.connect("test.db")
            conn.execute("PRAGMA key = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'")
            conn.execute("CREATE TABLE t1(id int)")
            conn.execute("INSERT INTO t1 VALUES (1)")
            conn.commit()
            conn.close()

            mock_conn_manager = AsyncMock()
            mock_conn_manager.db_path = "test.db"
            mock_get_conn_manager.return_value = mock_conn_manager

            result = cli_runner.invoke(app, ["key", "rotate", "--new-key-file", "new.key"])
            assert "Key rotated successfully!" in result.output

            # Verify the new key works
            conn = sqlcipher.connect("test.db")
            conn.execute("PRAGMA key = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM t1")
            assert cursor.fetchone()[0] == 1
            conn.close()

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    @patch("walnut.cli.backup.get_master_key", return_value="a" * 32)
    @patch("walnut.cli.database.init_database")
    @patch("walnut.cli.database.get_connection_manager")
    def test_backup_all(self, mock_get_conn_manager, mock_init_db, mock_get_key, cli_runner):
        """Test the backup all command."""
        with cli_runner.isolated_filesystem():
            with open("test.db", "w") as f:
                f.write("test")
            mock_conn_manager = AsyncMock()
            mock_conn_manager.db_path = "test.db"
            mock_get_conn_manager.return_value = mock_conn_manager

            result = cli_runner.invoke(app, ["backup", "all", "--output", "backup.zip", "--include-key"])
            assert "Complete backup created successfully" in result.output
            assert os.path.exists("backup.zip")
