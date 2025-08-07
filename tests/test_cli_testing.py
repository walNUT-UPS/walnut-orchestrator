from click.testing import CliRunner
from walnut.cli.main import app

class TestTestingCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_test_nut(self):
        result = self.runner.invoke(app, ['test', 'nut'])
        assert result.exit_code == 0
        assert "Testing NUT Server Connection" in result.output

    def test_test_database(self):
        result = self.runner.invoke(app, ['test', 'database'])
        assert result.exit_code == 0
        assert "Testing Database Functionality" in result.output

    def test_test_shutdown(self):
        result = self.runner.invoke(app, ['test', 'shutdown', 'somehost'])
        assert result.exit_code == 0
        assert "Testing Shutdown Process" in result.output
        assert "somehost" in result.output

    def test_test_all(self):
        result = self.runner.invoke(app, ['test', 'all'])
        assert result.exit_code == 0
        assert "Running All Tests" in result.output
