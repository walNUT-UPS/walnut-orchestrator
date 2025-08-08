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

from walnut.database.engine import get_master_key, _ensure_encrypted_database
from walnut.database.connection import init_database, close_database, get_connection_manager

@key_cli.command()
@click.option('--new-key-file', type=click.Path(exists=True, dir_okay=False, readable=True), required=True, help='Path to the new key file.')
@handle_async_command
async def rotate(new_key_file: str) -> None:
    """
    Rotates the master encryption key.
    """
    console.print("[bold yellow]Key Rotation[/bold yellow]")
    try:
        new_key = Path(new_key_file).read_text().strip()
        if len(new_key) < 32:
            console.print("[red]Error: New key must be at least 32 characters long.[/red]")
            sys.exit(1)

        await init_database(create_tables=False)
        manager = await get_connection_manager()
        db_path = manager.db_path
        old_key = get_master_key()

        if not db_path:
            raise DatabaseError("Database path not found in connection manager.")

        temp_db_path = f"{db_path}.new"

        # 1. Create a new encrypted database with the new key
        _ensure_encrypted_database(Path(temp_db_path), new_key)

        # 2. Attach the old database and copy the data
        from walnut.database.engine import sqlcipher
        conn = sqlcipher.connect(temp_db_path)
        conn.execute(f"PRAGMA key = '{new_key}'")
        conn.execute(f"ATTACH DATABASE '{db_path}' AS old_db KEY '{old_key}'")

        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM old_db.sqlite_master WHERE type='table'")
        for row in cursor.fetchall():
            conn.execute(row[0])

        cursor.execute("SELECT name FROM old_db.sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        for table in tables:
            table_name = table[0]
            cursor.execute(f"INSERT INTO main.{table_name} SELECT * FROM old_db.{table_name}")

        conn.commit()
        conn.close()

        # 3. Replace the old database with the new one
        Path(db_path).unlink()
        Path(temp_db_path).rename(db_path)

        console.print("[green]✅ Key rotated successfully![/green]")
        console.print("[yellow]NOTE: You must now update your WALNUT_DB_KEY environment variable.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error during key rotation: {e}[/red]")
        sys.exit(1)
    finally:
        await close_database()

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
