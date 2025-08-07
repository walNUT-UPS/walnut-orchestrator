import asyncio
import functools
import sys
from rich.console import Console

console = Console()

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
