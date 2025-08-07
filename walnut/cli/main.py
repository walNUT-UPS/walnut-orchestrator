"""
Main CLI application for walNUT UPS Management Platform.

Provides unified command-line interface for all walNUT operations including
database management, host management, and shutdown operations.
"""

import typer
from rich.console import Console

from walnut.cli import database, hosts

app = typer.Typer(
    name="walnut",
    help="walNUT UPS Management Platform - Network UPS Tools integration with coordinated shutdown",
    no_args_is_help=True,
)

console = Console()

# Add subcommands
app.add_typer(database.app, name="db", help="Database management commands")
app.add_typer(hosts.app, name="hosts", help="Host management and shutdown commands")

@app.command("version")
def show_version():
    """Show walNUT version information."""
    console.print("[bold]walNUT UPS Management Platform[/bold]")
    console.print("Version: 0.1.0")
    console.print("Network UPS Tools integration with coordinated shutdown")


@app.command("status")
def show_status():
    """Show walNUT system status."""
    console.print("[blue]walNUT System Status[/blue]")
    console.print("🔋 UPS Monitoring: [yellow]Not implemented yet[/yellow]")
    console.print("🖥️  Host Management: [green]Available[/green]")
    console.print("🔐 Database: [green]Available[/green]")
    console.print("⚡ Shutdown System: [green]Available[/green]")
    
    console.print("\n[dim]Use 'walnut hosts list' to see managed hosts")
    console.print("Use 'walnut db version' to check database status")


if __name__ == "__main__":
    app()