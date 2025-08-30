from unittest.mock import patch
import pytest
pytest.skip("CLI tests skipped by default; pending update", allow_module_level=True)
from walnut.cli.main import app

@pytest.mark.usefixtures("mock_create_database_engine")
class TestTestingCLI:
    @patch('walnut.cli.test.PyNUTClient')
    def test_test_nut(self, mock_pynut, cli_runner):
        """Test the test nut command."""
        mock_client = mock_pynut.return_value
        mock_client.list_ups.return_value = {"ups": "data"}
        result = cli_runner.invoke(app, ['test', 'nut'])
        assert "NUT server connection successful!" in result.output

    @patch('walnut.cli.test.get_db_session')
    async def test_test_database(self, mock_get_db_session, cli_runner, mock_db_session):
        """Test the test database command."""
        mock_get_db_session.return_value = mock_db_session

        from walnut.cli.test import database
        # We need to run the callback directly because of the async test
        await database.callback(samples=10)

    def test_test_shutdown(self, cli_runner):
        """Test the test shutdown command."""
        result = cli_runner.invoke(app, ['test', 'shutdown', 'somehost'])
        assert "not yet implemented" in result.output

    def test_test_all(self, cli_runner):
        """Test the test all command."""
        result = cli_runner.invoke(app, ['test', 'all'])
        assert result.exit_code == 0
        assert "Running All Tests" in result.output
