import click
import sys
from pathlib import Path
from rich.console import Console
import os
from rich.console import Console

console = Console()

@click.group(name='key')
def key_cli():
    """Key management commands."""
    pass

@key_cli.command()
def validate():
    """
    Validates the current encryption key.
    """
    console.print("[bold blue]Validating Encryption Key[/bold blue]")
    key = os.environ.get("WALNUT_DB_KEY")
    if key:
        console.print(f"[green]✅ Master key loaded successfully[/green]")
        key_length = len(key)
        console.print(f"Key length: {key_length} characters")
        if key_length < 32:
            console.print("[red]⚠️  WARNING: Key is shorter than recommended 32 characters[/red]")
        else:
            console.print("[green]✅ Key length meets security requirements[/green]")
    else:
        console.print("[red]❌ WALNUT_DB_KEY environment variable not set.[/red]")
