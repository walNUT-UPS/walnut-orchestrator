from click.testing import CliRunner
from walnut.cli.main import app

class TestSystemCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_system_status(self):
        result = self.runner.invoke(app, ['system', 'status'])
        assert result.exit_code == 0
        assert "System Status" in result.output

    def test_system_health(self):
        result = self.runner.invoke(app, ['system', 'health'])
        assert result.exit_code == 0
        assert "System Health Check" in result.output

    def test_config_export(self):
        result = self.runner.invoke(app, ['system', 'config', 'export'])
        assert result.exit_code == 0
        assert "Exporting Configuration" in result.output

    def test_config_validate(self):
        result = self.runner.invoke(app, ['system', 'config', 'validate'])
        assert result.exit_code == 0
        assert "Validating Configuration" in result.output
