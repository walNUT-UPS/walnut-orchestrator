
import click
import logging
import os
import sys
from rich.console import Console
from pydantic import ValidationError

from .database import db_cli
from .keys import key_cli
from .test import test_cli
from .system import system_cli
from .hosts import hosts_cli
from .backup import backup_cli
from .auth import auth_cli

console = Console()


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enables verbose mode.')
@click.option('--quiet', '-q', is_flag=True, help='Enables quiet mode.')
@click.pass_context
def app(ctx, verbose, quiet):
    """
    walNUT UPS Management Platform CLI.
    """
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose
    ctx.obj['QUIET'] = quiet

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.INFO)

    from walnut.database.engine import init_db
    if os.getenv("WALNUT_TESTING") == "true":
        db_url = os.environ.get("WALNUT_DB_URL") or f"sqlite+pysqlite:///{os.getenv('WALNUT_DB_PATH','/tmp/test.db')}"
    else:
        db_url = os.environ.get("DATABASE_URL")

    if db_url:
        init_db(db_url)

# Add subcommands
app.add_command(db_cli, name='db')
app.add_command(key_cli, name='key')
app.add_command(test_cli, name='test')
app.add_command(system_cli, name='system')
app.add_command(hosts_cli, name='hosts')
app.add_command(backup_cli, name='backup')
app.add_command(auth_cli, name='auth')

if __name__ == '__main__':
    app()
