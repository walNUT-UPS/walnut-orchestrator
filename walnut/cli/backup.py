import click
from rich.console import Console

console = Console()

@click.group(name='backup')
def backup_cli():
    """Backup commands."""
    pass

import os
import zipfile
import tempfile
from pathlib import Path

from walnut.cli.database import backup as db_backup
from walnut.database.engine import get_master_key

@backup_cli.command(name='all')
@click.option('--include-key', is_flag=True, help='Includes the encryption key in the backup.')
@click.option('--output', type=click.Path(), required=True, help='Path to save the backup file.')
@click.pass_context
def all_cmd(ctx, include_key, output):
    """
    Performs a complete backup of the application, including the database and optionally the key.
    """
    console.print(f"[bold blue]Complete Backup to {output}[/bold blue]")

    with tempfile.TemporaryDirectory() as temp_dir:
        db_backup_path = Path(temp_dir) / "walnut.db"

        # 1. Backup the database
        ctx.invoke(db_backup, output=str(db_backup_path))

        # 2. Prepare the key if requested
        key = None
        if include_key:
            console.print("[yellow]⚠️  WARNING: Including the master encryption key in the backup is a security risk. Store the backup securely and do not share it with untrusted parties.[/yellow]")
            key = get_master_key()

        # 3. Create a zip archive
        with zipfile.ZipFile(output, 'w') as zipf:
            zipf.write(db_backup_path, arcname="walnut.db")
            if key is not None:
                zipf.writestr("walnut.key", key)

    console.print(f"[green]✅ Complete backup created successfully at {output}[/green]")
