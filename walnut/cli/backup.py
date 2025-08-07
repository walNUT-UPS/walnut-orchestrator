import click
from rich.console import Console

console = Console()

@click.group(name='backup')
def backup_cli():
    """Backup commands."""
    pass

@backup_cli.command(name='all')
@click.option('--include-key', is_flag=True, help='Includes the encryption key in the backup.')
@click.option('--output', type=click.Path(), required=True, help='Path to save the backup file.')
def all_cmd(include_key, output):
    """
    Performs a complete backup of the application, including the database and optionally the key.
    """
    console.print(f"[bold blue]Complete Backup[/bold blue]")
    console.print(f"Output path: {output}")
    console.print(f"Include key: {'Yes' if include_key else 'No'}")
    console.print("[green]Placeholder: Backup logic would be executed here.[/green]")
