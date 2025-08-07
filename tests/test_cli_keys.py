from click.testing import CliRunner
from walnut.cli.main import app
from unittest.mock import patch
import os

class TestKeysCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_key_rotate(self):
        with self.runner.isolated_filesystem():
            with open('new_key.txt', 'w') as f:
                f.write('a' * 32)
            result = self.runner.invoke(app, ['key', 'rotate', '--new-key-file', 'new_key.txt'])
            assert result.exit_code == 0
            assert "Key Rotation" in result.output

    @patch.dict(os.environ, {"WALNUT_DB_KEY": "a" * 32})
    def test_key_validate(self):
        result = self.runner.invoke(app, ['key', 'validate'])
        assert result.exit_code == 0
        assert "Validating Encryption Key" in result.output

    def test_backup_all(self):
        result = self.runner.invoke(app, ['backup', 'all', '--output', 'backup.zip'])
        assert result.exit_code == 0
        assert "Complete Backup" in result.output
