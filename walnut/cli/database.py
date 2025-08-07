"""
Database management CLI commands for walNUT.

Provides command-line interface for database operations including:
- Database initialization and migration
- Health checks and diagnostics  
- Schema version management
- Data export/import utilities
- Maintenance operations
"""

import asyncio
import functools
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from sqlalchemy import text

from ..database.connection import (
    ConnectionManager,
    close_database,
    init_database,
    get_connection_manager,
)
from ..database.engine import DatabaseError, get_master_key
from ..database.models import Base

# Initialize CLI app and console
app = typer.Typer(
    name="walnut-db",
    help="walNUT Database Management Commands",
    add_completion=False,
)
console = Console()

# Configure logging for CLI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def handle_async_command(async_func):
    """Decorator to handle async CLI commands."""
    @functools.wraps(async_func)
    def wrapper(*args, **kwargs):
        try:
            return asyncio.run(async_func(*args, **kwargs))
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
    return wrapper


@app.command()
@handle_async_command
async def init(
    db_path: Optional[str] = typer.Option(
        None,
        "--db-path",
        "-d", 
        help="Database file path (default: data/walnut.db)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force initialization even if database exists"
    ),
    echo: bool = typer.Option(
        False,
        "--echo",
        help="Echo SQL statements for debugging"
    ),
) -> None:
    """
    Initialize the walNUT database with encryption and schema.
    """
    console.print("[bold blue]Initializing walNUT Database[/bold blue]")
    
    # Check if database exists
    db_file = Path(db_path) if db_path else Path("data/walnut.db")
    if db_file.exists() and not force:
        console.print(f"[yellow]Database already exists at {db_file}[/yellow]")
        console.print("Use --force to reinitialize")
        return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        # Initialize database
        task = progress.add_task("Setting up database engine...", total=None)
        try:
            diagnostics = await init_database(
                db_path=str(db_file) if db_path else None,
                echo=echo,
                create_tables=True,
            )
            progress.update(task, description="Database initialized successfully!")
            
        except DatabaseError as e:
            progress.stop()
            console.print(f"[red]Database initialization failed: {e}[/red]")
            return
        finally:
            await close_database()
    
    # Display results
    console.print("\n[green]✅ Database initialized successfully![/green]")
    
    # Show diagnostics in a table
    table = Table(title="Database Diagnostics")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")
    
    for key, value in diagnostics.items():
        if isinstance(value, bool):
            value_str = "✅ Yes" if value else "❌ No"
        elif value is None:
            value_str = "[dim]Not available[/dim]"
        else:
            value_str = str(value)
        table.add_row(key.replace("_", " ").title(), value_str)
    
    console.print(table)


@app.command()
@handle_async_command
async def health(
    db_path: Optional[str] = typer.Option(
        None,
        "--db-path", 
        "-d",
        help="Database file path"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output in JSON format"
    ),
) -> None:
    """
    Check database health and connection status.
    """
    try:
        await init_database(
            db_path=db_path,
            create_tables=False,
        )
        
        manager = await get_connection_manager()
        health_status = await manager.health_check()
        
        if json_output:
            console.print(JSON(json.dumps(health_status, indent=2)))
        else:
            # Display health status with rich formatting
            if health_status["healthy"]:
                console.print("[green]✅ Database is healthy[/green]")
            else:
                console.print("[red]❌ Database health check failed[/red]")
                console.print(f"[red]Error: {health_status.get('error', 'Unknown error')}[/red]")
                return
            
            # Engine diagnostics table
            if "engine_diagnostics" in health_status:
                diag = health_status["engine_diagnostics"]
                table = Table(title="Engine Diagnostics")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="magenta")
                
                for key, value in diag.items():
                    if isinstance(value, bool):
                        value_str = "✅ Yes" if value else "❌ No" 
                    elif value is None:
                        value_str = "[dim]Not available[/dim]"
                    else:
                        value_str = str(value)
                    table.add_row(key.replace("_", " ").title(), value_str)
                
                console.print(table)
            
            # Pool status table
            if "pool_status" in health_status:
                pool = health_status["pool_status"]
                pool_table = Table(title="Connection Pool Status")
                pool_table.add_column("Metric", style="cyan")
                pool_table.add_column("Value", style="magenta")
                
                for key, value in pool.items():
                    pool_table.add_row(key.replace("_", " ").title(), str(value))
                
                console.print(pool_table)
                
    except Exception as e:
        if json_output:
            error_response = {"healthy": False, "error": str(e)}
            console.print(JSON(json.dumps(error_response, indent=2)))
        else:
            console.print(f"[red]Health check failed: {e}[/red]")
        sys.exit(1)
    finally:
        await close_database()


@app.command()
@handle_async_command  
async def info(
    db_path: Optional[str] = typer.Option(
        None,
        "--db-path",
        "-d", 
        help="Database file path"
    ),
) -> None:
    """
    Display database information and statistics.
    """
    try:
        await init_database(
            db_path=db_path,
            create_tables=False,
        )
        
        manager = await get_connection_manager()
        
        # Get table information
        async with manager.get_session() as session:
            # Get table list and row counts
            tables_info = []
            for table_name in Base.metadata.tables.keys():
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    )
                    row_count = result.scalar()
                    tables_info.append((table_name, row_count))
                except Exception as e:
                    tables_info.append((table_name, f"Error: {e}"))
            
            # Get database file size
            try:
                size_result = await session.execute(text("PRAGMA page_count"))
                page_count = size_result.scalar()
                page_size_result = await session.execute(text("PRAGMA page_size"))
                page_size = page_size_result.scalar()
                db_size = page_count * page_size if page_count and page_size else None
            except Exception:
                db_size = None
            
            # Get some database settings
            settings = {}
            for pragma in ["journal_mode", "synchronous", "cache_size", "foreign_keys"]:
                try:
                    result = await session.execute(text(f"PRAGMA {pragma}"))
                    settings[pragma] = result.scalar()
                except Exception:
                    settings[pragma] = "Unknown"
        
        # Display information
        console.print("[bold blue]walNUT Database Information[/bold blue]\n")
        
        # Database settings
        settings_table = Table(title="Database Settings")
        settings_table.add_column("Setting", style="cyan")
        settings_table.add_column("Value", style="magenta")
        
        if db_size:
            settings_table.add_row("Database Size", f"{db_size:,} bytes ({db_size/1024/1024:.2f} MB)")
        
        for key, value in settings.items():
            settings_table.add_row(key.replace("_", " ").title(), str(value))
        
        console.print(settings_table)
        
        # Tables information
        if tables_info:
            tables_table = Table(title="Tables")
            tables_table.add_column("Table Name", style="cyan")
            tables_table.add_column("Row Count", style="magenta")
            
            for table_name, row_count in tables_info:
                tables_table.add_row(table_name, str(row_count))
            
            console.print(tables_table)
            
    except Exception as e:
        console.print(f"[red]Failed to get database info: {e}[/red]")
        sys.exit(1)
    finally:
        await close_database()


@app.command()
@handle_async_command
async def reset(
    db_path: Optional[str] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Database file path"
    ),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt"
    ),
) -> None:
    """
    Reset database by dropping and recreating all tables.
    
    WARNING: This will delete ALL data!
    """
    if not confirm:
        console.print("[red]⚠️  WARNING: This will delete ALL database data![/red]")
        confirmed = typer.confirm("Are you sure you want to continue?")
        if not confirmed:
            console.print("Operation cancelled")
            return
    
    try:
        await init_database(
            db_path=db_path,
            create_tables=False,
        )
        
        manager = await get_connection_manager()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Dropping tables...", total=None)
            await manager.drop_tables()
            
            progress.update(task, description="Creating tables...")
            await manager.create_tables()
            
            progress.update(task, description="Database reset complete!")
        
        console.print("[green]✅ Database reset successfully![/green]")
        
    except Exception as e:
        console.print(f"[red]Database reset failed: {e}[/red]")
        sys.exit(1)
    finally:
        await close_database()


@app.command()
@handle_async_command
async def test_encryption() -> None:
    """
    Test database encryption setup and master key access.
    """
    console.print("[bold blue]Testing Encryption Setup[/bold blue]\n")
    
    # Test master key access
    try:
        console.print("Testing master key access...")
        master_key = get_master_key()
        key_length = len(master_key)
        
        console.print(f"[green]✅ Master key loaded successfully[/green]")
        console.print(f"Key length: {key_length} characters")
        
        if key_length < 32:
            console.print("[red]⚠️  WARNING: Key is shorter than recommended 32 characters[/red]")
        else:
            console.print("[green]✅ Key length meets security requirements[/green]")
            
    except Exception as e:
        console.print(f"[red]❌ Master key test failed: {e}[/red]")
        return
    
    # Test database creation with encryption
    try:
        console.print("\nTesting encrypted database creation...")
        test_db_path = "test_encryption.db"
        
        await init_database(
            db_path=test_db_path,
            create_tables=True,
        )
        
        manager = await get_connection_manager()
        health_status = await manager.health_check()
        
        if health_status.get("healthy", False):
            engine_diag = health_status.get("engine_diagnostics", {})
            encryption_enabled = engine_diag.get("encryption_enabled", False)
            
            if encryption_enabled:
                console.print("[green]✅ Database encryption is working[/green]")
                cipher_version = engine_diag.get("cipher_version")
                if cipher_version:
                    console.print(f"Cipher version: {cipher_version}")
            else:
                console.print("[red]❌ Database encryption not detected[/red]")
        else:
            console.print(f"[red]❌ Database health check failed[/red]")
        
        # Cleanup
        await close_database()
        test_db_file = Path(test_db_path)
        if test_db_file.exists():
            test_db_file.unlink()
            console.print("Test database cleaned up")
            
    except Exception as e:
        console.print(f"[red]❌ Encryption test failed: {e}[/red]")
        await close_database()


@app.command()
def version() -> None:
    """
    Display walNUT database version information.
    """
    from .. import __version__
    
    console.print(f"[bold blue]walNUT Database CLI[/bold blue]")
    console.print(f"Version: {__version__}")
    console.print("SQLCipher-based encrypted SQLite storage")


if __name__ == "__main__":
    app()