import click
import json
from rich.console import Console
from rich.json import JSON

console = Console()

@click.group(name='system')
def system_cli():
    """System status and health commands."""
    pass

from walnut.database.connection import get_database_health
from walnut import __version__
from .utils import handle_async_command

@system_cli.command()
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format.')
@handle_async_command
async def status(json_output: bool) -> None:
    """Shows the system status."""
    console.print("[bold blue]System Status[/bold blue]")
    db_health = await get_database_health()
    status_data = {
        "service": "walNUT",
        "version": __version__,
        "database_status": "Healthy" if db_health.get("healthy") else "Unhealthy",
        "database_details": db_health,
    }
    if json_output:
        console.print(JSON(json.dumps(status_data, indent=2)))
    else:
        for key, value in status_data.items():
            if isinstance(value, dict):
                console.print(f"[cyan]{key.replace('_', ' ').title()}[/cyan]:")
                for sub_key, sub_value in value.items():
                    console.print(f"  [green]{sub_key.replace('_', ' ').title()}[/green]: {sub_value}")
            else:
                console.print(f"[cyan]{key.replace('_', ' ').title()}[/cyan]: {value}")


@system_cli.command()
@click.option('--detailed', is_flag=True, help='Show detailed health information.')
@handle_async_command
async def health(detailed: bool) -> None:
    """Checks the system health."""
    console.print("[bold blue]System Health Check[/bold blue]")
    db_health = await get_database_health()
    health_data = {
        "database_connection": "OK" if db_health.get("healthy") else "FAIL",
        "nut_server_connection": "UNKNOWN", # Placeholder
        "last_backup": "UNKNOWN", # Placeholder
    }
    if detailed:
        health_data["details"] = db_health

    for key, value in health_data.items():
        if isinstance(value, dict):
            console.print(f"[cyan]{key.replace('_', ' ').title()}[/cyan]:")
            for sub_key, sub_value in value.items():
                console.print(f"  [green]{sub_key.replace('_', ' ').title()}[/green]: {sub_value}")
        else:
            console.print(f"[cyan]{key.replace('_', ' ').title()}[/cyan]: {value}")


@system_cli.group(name='config')
def config_cli():
    """Configuration commands."""
    pass

@config_cli.command()
@click.option('--output', type=click.Path(), help='Path to save the configuration file.')
def export(output):
    """Exports the configuration."""
    console.print("[bold blue]Exporting Configuration[/bold blue]")
    if output:
        console.print(f"Exporting to: {output}")
    # In a real implementation, you would gather all config sources and export them.
    console.print("[green]Placeholder: Config export logic would be executed here.[/green]")

@config_cli.command()
def validate():
    """Validates the configuration."""
    console.print("[bold blue]Validating Configuration[/bold blue]")
    # This would check for missing required config values, etc.
    console.print("[green]Placeholder: Config validation logic would be executed here.[/green]")
