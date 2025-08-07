from click.testing import CliRunner
from walnut.cli.main import app

class TestHostsCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_hosts_list(self):
        result = self.runner.invoke(app, ['hosts', 'list'])
        assert result.exit_code == 0
        assert "Managed Hosts" in result.output

    def test_hosts_add(self):
        with self.runner.isolated_filesystem():
            with open('key.txt', 'w') as f:
                f.write('fakekey')
            result = self.runner.invoke(app, ['hosts', 'add', 'new-host', '--ip', '1.2.3.4', '--ssh-key', 'key.txt', '--user', 'test'])
            assert result.exit_code == 0
            assert "Adding Host" in result.output

    def test_hosts_remove(self):
        result = self.runner.invoke(app, ['hosts', 'remove', 'some-host'])
        assert result.exit_code == 0
        assert "Removing Host" in result.output

    def test_hosts_test(self):
        result = self.runner.invoke(app, ['hosts', 'test', 'some-host'])
        assert result.exit_code == 0
        assert "Testing Host" in result.output
