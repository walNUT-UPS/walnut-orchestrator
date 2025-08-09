import json
import pytest
from click.testing import CliRunner
from walnut.cli.main import app

pytestmark = pytest.mark.usefixtures("test_db")


def test_create_admin(cli_runner: CliRunner):
    result = cli_runner.invoke(
        app,
        [
            "auth",
            "create-admin",
            "--email",
            "admin@example.com",
            "--password",
            "password",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Admin user admin@example.com created successfully!" in result.output


def test_list_users(cli_runner: CliRunner):
    # Create a user first
    cli_runner.invoke(
        app,
        [
            "auth",
            "create-admin",
            "--email",
            "admin@example.com",
            "--password",
            "password",
        ],
    )

    result = cli_runner.invoke(app, ["auth", "list-users"])
    assert result.exit_code == 0
    assert "admin@example.com" in result.output

    result = cli_runner.invoke(app, ["auth", "list-users", "--json"])
    assert result.exit_code == 0
    users = json.loads(result.output)
    assert len(users) == 1
    assert users[0]["email"] == "admin@example.com"


def test_set_role(cli_runner: CliRunner):
    cli_runner.invoke(
        app,
        ["auth", "create-admin", "--email", "user@example.com", "--password", "password"],
    )
    result = cli_runner.invoke(
        app, ["auth", "set-role", "user@example.com", "--role", "viewer"]
    )
    assert result.exit_code == 0
    assert "Role for user@example.com set to viewer" in result.output


def test_disable_enable(cli_runner: CliRunner):
    cli_runner.invoke(
        app,
        ["auth", "create-admin", "--email", "user@example.com", "--password", "password"],
    )

    result = cli_runner.invoke(app, ["auth", "disable", "user@example.com"])
    assert result.exit_code == 0
    assert "User user@example.com disabled." in result.output

    result = cli_runner.invoke(app, ["auth", "enable", "user@example.com"])
    assert result.exit_code == 0
    assert "User user@example.com enabled." in result.output


def test_reset_password(cli_runner: CliRunner):
    cli_runner.invoke(
        app,
        ["auth", "create-admin", "--email", "user@example.com", "--password", "password"],
    )
    result = cli_runner.invoke(
        app,
        [
            "auth",
            "reset-password",
            "user@example.com",
            "--password",
            "new-password",
        ],
        input="new-password\n",
    )
    assert result.exit_code == 0
    assert "Password for user@example.com reset." in result.output
