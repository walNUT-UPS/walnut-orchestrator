import click
import sys
from pathlib import Path
from rich.console import Console
from ..database.engine import get_master_key, DatabaseError
from .utils import handle_async_command

console = Console()

@click.group(name='key')
def key_cli():
    """Key management commands."""
    pass

from walnut.database.connection import init_database, close_database, get_connection_manager

# @key_cli.command()
# @click.option('--new-key-file', type=click.Path(exists=True, dir_okay=False, readable=True), required=True, help='Path to the new key file.')
# @handle_async_command
# async def rotate(new_key_file: str) -> None:
#     """
#     Rotates the master encryption key. (Temporarily disabled)
#     """
#     console.print("[bold yellow]Key Rotation (Temporarily Disabled)[/bold yellow]")
#     console.print("This feature is being refactored to work with the new database driver.")
#     sys.exit(1)

@key_cli.command()
def validate():
    """
    Validates the current encryption key.
    """
    console.print("[bold blue]Validating Encryption Key[/bold blue]")
    try:
        master_key = get_master_key()
        key_length = len(master_key)

        console.print(f"[green]✅ Master key loaded successfully[/green]")
        console.print(f"Key length: {key_length} characters")

        if key_length < 32:
            console.print("[red]⚠️  WARNING: Key is shorter than recommended 32 characters[/red]")
        else:
            console.print("[green]✅ Key length meets security requirements[/green]")

    except DatabaseError as e:
        console.print(f"[red]❌ Key validation failed: {e}[/red]")
        sys.exit(1)
