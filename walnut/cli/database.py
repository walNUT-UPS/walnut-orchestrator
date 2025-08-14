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

import click
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from sqlalchemy import text

from ..database.engine import SessionLocal, engine
from ..database.models import Base

# Initialize console
console = Console()

# Configure logging for CLI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group(name="db")
def db_cli():
    """walNUT Database Management Commands"""
    pass

@db_cli.command()
def init() -> None:
    """
    Initialize the walNUT database with encryption and schema.
    """
    console.print("[bold blue]Initializing walNUT Database[/bold blue]")
    try:
        Base.metadata.create_all(engine)
        console.print("[green]✅ Database initialized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Database initialization failed: {e}[/red]")


@db_cli.command()
def health() -> None:
    """
    Check database health and connection status.
    """
    try:
        connection = engine.connect()
        connection.close()
        console.print("[green]✅ Database is healthy[/green]")
    except Exception as e:
        console.print(f"[red]Health check failed: {e}[/red]")


@db_cli.command()
def stats() -> None:
    """
    Display database information and statistics.
    """
    session = SessionLocal()
    try:
        # Get table information
        tables_info = []
        for table_name in Base.metadata.tables.keys():
            try:
                result = session.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                )
                row_count = result.scalar()
                # Ensure row count is an integer for consistent display
                try:
                    row_count = int(row_count) if row_count is not None else 0
                except (ValueError, TypeError):
                    row_count = 0
                tables_info.append((table_name, row_count))
            except Exception as e:
                tables_info.append((table_name, f"Error: {e}"))

        # Get database file size
        try:
            page_count_result = session.execute(text("PRAGMA page_count")).scalar()
            page_size_result = session.execute(text("PRAGMA page_size")).scalar()
            
            if page_count_result is not None and page_size_result is not None:
                try:
                    page_count = int(page_count_result)
                    page_size = int(page_size_result)
                    db_size = page_count * page_size if page_count > 0 and page_size > 0 else 0
                except (ValueError, TypeError):
                    db_size = 0
            else:
                db_size = 0
        except Exception:
            db_size = 0

        # Get some database settings
        settings = {}
        for pragma in ["journal_mode", "synchronous", "cache_size", "foreign_keys"]:
            try:
                result = session.execute(text(f"PRAGMA {pragma}")).scalar()
                # Convert to string for display, handling potential type issues
                settings[pragma] = str(result) if result is not None else "Unknown"
            except Exception:
                settings[pragma] = "Unknown"
        
        # Display information
        console.print("[bold blue]walNUT Database Information[/bold blue]\n")
        
        # Database settings
        settings_table = Table(title="Database Settings")
        settings_table.add_column("Setting", style="cyan")
        settings_table.add_column("Value", style="magenta")
        
        if isinstance(db_size, int) and db_size > 0 and db_size < 10**12:
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
    finally:
        session.close()


@db_cli.command()
@click.option(
    "--yes",
    "-y",
    "confirm",
    is_flag=True,
    help="Skip confirmation prompt"
)
def reset(confirm: bool) -> None:
    """
    Reset database by dropping and recreating all tables.
    
    WARNING: This will delete ALL data!
    """
    if not confirm:
        console.print("[red]⚠️  WARNING: This will delete ALL database data![/red]")
        confirmed = click.confirm("Are you sure you want to continue?")
        if not confirmed:
            console.print("Operation cancelled")
            return
    
    try:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        console.print("[green]✅ Database reset successfully![/green]")
    except Exception as e:
        console.print(f"[red]Database reset failed: {e}[/red]")

@db_cli.command()
def version() -> None:
    """
    Display walNUT database version information.
    """
    from .. import __version__
    
    console.print(f"[bold blue]walNUT Database CLI[/bold blue]")
    console.print(f"Version: {__version__}")
    console.print("SQLCipher-based encrypted SQLite storage")

@db_cli.command()
def vacuum() -> None:
    """Vacuums the database to reclaim space."""
    console.print("[bold blue]Vacuuming Database[/bold blue]")
    try:
        with engine.connect() as connection:
            connection.execute(text("VACUUM"))
        console.print("[green]✅ Database vacuumed successfully![/green]")
    except Exception as e:
        console.print(f"[red]Failed to vacuum database: {e}[/red]")
