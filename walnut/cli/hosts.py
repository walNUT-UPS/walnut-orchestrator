import click
import json
from rich.console import Console
from rich.json import JSON
from .utils import handle_async_command

console = Console()

@click.group(name='hosts')
def hosts_cli():
    """Host management commands."""
    pass

from walnut.database.models import Host
from walnut.database.connection import get_db_session
from sqlalchemy import select

@hosts_cli.command(name="list")
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format.')
@handle_async_command
async def list_hosts(json_output: bool) -> None:
    """Lists all hosts."""
    console.print("[bold blue]Managed Hosts[/bold blue]")
    async with get_db_session() as session:
        result = await session.execute(select(Host))
        hosts = result.scalars().all()
        if json_output:
            hosts_data = [
                {
                    "id": host.id,
                    "hostname": host.hostname,
                    "ip_address": host.ip_address,
                    "os_type": host.os_type,
                    "connection_type": host.connection_type,
                }
                for host in hosts
            ]
            console.print(JSON(json.dumps(hosts_data)))
        else:
            for host in hosts:
                console.print(f"- [cyan]{host.hostname}[/cyan] ({host.ip_address})")

@hosts_cli.command()
@click.argument('name')
@click.option('--ip', required=True, help='IP address of the host.')
@click.option('--ssh-key', type=click.Path(exists=True), required=True, help='Path to the SSH key.')
@click.option('--user', required=True, help='SSH user for the host.')
@handle_async_command
async def add(name: str, ip: str, ssh_key: str, user: str) -> None:
    """Adds a new host."""
    console.print(f"[bold blue]Adding Host: {name}[/bold blue]")
    new_host = Host(
        hostname=name,
        ip_address=ip,
        connection_type="ssh",
        host_metadata={"ssh_user": user, "ssh_key_path": ssh_key},
    )
    async with get_db_session() as session:
        session.add(new_host)
        await session.commit()
    console.print(f"[green]✅ Host '{name}' added successfully![/green]")

@hosts_cli.command()
@click.argument('name')
@handle_async_command
async def remove(name: str) -> None:
    """Removes a host."""
    console.print(f"[bold blue]Removing Host: {name}[/bold blue]")
    async with get_db_session() as session:
        result = await session.execute(select(Host).where(Host.hostname == name))
        host = result.scalar_one_or_none()
        if host:
            await session.delete(host)
            await session.commit()
            console.print(f"[green]✅ Host '{name}' removed successfully![/green]")
        else:
            console.print(f"[red]Host '{name}' not found.[/red]")

@hosts_cli.command()
@click.argument('name')
def test(name: str) -> None:
    """
    Tests a host connection.

    NOTE: This command is not yet implemented.
    """
    console.print(f"[bold blue]Testing Host: {name}[/bold blue]")
    console.print("[red]This command is not yet implemented.[/red]")
