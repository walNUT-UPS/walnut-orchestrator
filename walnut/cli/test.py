import click
from rich.console import Console

console = Console()

@click.group(name='test')
def test_cli():
    """Testing and validation commands."""
    pass

from pynut2.nut2 import PyNUTClient, PyNUTError
from .utils import handle_async_command

@test_cli.command()
@click.option('--host', default='10.240.0.239', help='NUT server host.')
@click.option('--port', default=3493, help='NUT server port.')
def nut(host: str, port: int) -> None:
    """Tests NUT server connection."""
    console.print(f"[bold blue]Testing NUT Server Connection to {host}:{port}[/bold blue]")
    try:
        client = PyNUTClient(host=host, port=port)
        # This will fail as we can't connect, but it's the right logic
        client.list_ups()
        console.print("[green]✅ NUT server connection successful![/green]")
    except PyNUTError as e:
        console.print(f"[red]❌ NUT server connection failed: {e}[/red]")

from walnut.database.connection import get_db_session
from walnut.database.models import UPSSample
from sqlalchemy import select, delete
import anyio
import time

@test_cli.command()
@click.option('--samples', default=100, help='Number of sample data points to create.')
@handle_async_command
async def database(samples: int) -> None:
    """Tests database functionality by writing and reading sample data."""
    console.print(f"[bold blue]Testing Database Functionality with {samples} samples[/bold blue]")

    start_time = time.time()
    async with get_db_session() as session:
        # Clean up old test data
        await anyio.to_thread.run_sync(session.execute, delete(UPSSample).where(UPSSample.status == "TESTING"))

        # Write new samples
        for i in range(samples):
            sample = UPSSample(charge_percent=float(i), status="TESTING")
            session.add(sample)
        # commit is handled by the context manager
    write_time = time.time() - start_time
    console.print(f"Write test completed in {write_time:.2f} seconds.")

    start_time = time.time()
    async with get_db_session() as session:
        result = await anyio.to_thread.run_sync(session.execute, select(UPSSample).where(UPSSample.status == "TESTING"))
        read_samples = await anyio.to_thread.run_sync(result.scalars().all)
    read_time = time.time() - start_time
    console.print(f"Read test completed in {read_time:.2f} seconds.")

    assert len(read_samples) == samples
    console.print("[green]✅ Database test successful![/green]")

@test_cli.command()
@click.argument('host')
@click.option('--dry-run', is_flag=True, help="Simulate shutdown without actually running commands.")
def shutdown(host, dry_run):
    """Tests shutdown process for a given host."""
    console.print(f"[bold blue]Testing Shutdown Process[/bold blue]")
    console.print(f"Host: {host}")
    console.print(f"Dry run: {'Yes' if dry_run else 'No'}")
    # This would test the SSH connection and shutdown command for a host.
    console.print("[green]Placeholder: Shutdown test logic would be executed here.[/green]")

@test_cli.command()
def all():
    """Runs all tests."""
    console.print(f"[bold blue]Running All Tests[/bold blue]")
    console.print("This would run NUT, database, and shutdown tests.")
    console.print("[green]Placeholder: Logic to run all tests would be executed here.[/green]")
