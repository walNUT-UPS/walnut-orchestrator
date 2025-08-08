import os
from unittest.mock import patch
import pytest
from walnut.cli.main import app

@pytest.mark.usefixtures("mock_create_database_engine")
class TestHostsCLI:
    @patch('walnut.cli.hosts.get_db_session')
    def test_hosts_list(self, mock_get_db_session, cli_runner, mock_db_session):
        """Test the hosts list command."""
        mock_get_db_session.return_value = mock_db_session
        result = cli_runner.invoke(app, ['hosts', 'list'])
        assert "Managed Hosts" in result.output

    @patch('walnut.cli.hosts.get_db_session')
    def test_hosts_add(self, mock_get_db_session, cli_runner, mock_db_session):
        """Test the hosts add command."""
        mock_get_db_session.return_value = mock_db_session
        with cli_runner.isolated_filesystem():
            with open('key.txt', 'w') as f:
                f.write('fakekey')
            result = cli_runner.invoke(app, ['hosts', 'add', 'new-host', '--ip', '1.2.3.4', '--ssh-key', 'key.txt', '--user', 'test'])
            assert "Host 'new-host' added successfully!" in result.output

    @patch('walnut.cli.hosts.get_db_session')
    def test_hosts_remove(self, mock_get_db_session, cli_runner, mock_db_session):
        """Test the hosts remove command."""
        mock_get_db_session.return_value = mock_db_session
        result = cli_runner.invoke(app, ['hosts', 'remove', 'some-host'])
        assert "Host 'some-host' removed successfully!" in result.output

    def test_hosts_test(self, cli_runner):
        """Test the hosts test command."""
        result = cli_runner.invoke(app, ['hosts', 'test', 'some-host'])
        assert "not yet implemented" in result.output
