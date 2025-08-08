
import click
import logging
from rich.console import Console

from .database import db_cli
from .keys import key_cli
from .test import test_cli
from .system import system_cli
from .hosts import hosts_cli
from .backup import backup_cli


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

# Add subcommands
app.add_command(db_cli, name='db')
app.add_command(key_cli, name='key')
app.add_command(test_cli, name='test')
app.add_command(system_cli, name='system')
app.add_command(hosts_cli, name='hosts')
app.add_command(backup_cli, name='backup')

if __name__ == '__main__':
    app()
