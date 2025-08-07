"""
Host management CLI commands for walNUT.

Provides command-line interface for managing SSH hosts, testing connections,
and executing shutdown operations.
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from walnut.cli.database import handle_async_command
from walnut.hosts.manager import HostManager, HostDiscovery
from walnut.shutdown.executor import ShutdownExecutor
from walnut.shutdown.triggers import ShutdownTriggerManager, TriggerCondition

app = typer.Typer(help="Host management commands for SSH and shutdown operations")
console = Console()

# Initialize managers
host_manager = HostManager()
shutdown_executor = ShutdownExecutor()
trigger_manager = ShutdownTriggerManager()


@app.command("add")
@handle_async_command
async def add_host(
    hostname: str = typer.Argument(..., help="Host name or identifier"),
    ip: Optional[str] = typer.Option(None, "--ip", help="IP address (auto-resolved if not provided)"),
    username: str = typer.Option("root", "--user", "-u", help="SSH username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="SSH password"),
    key_path: Optional[str] = typer.Option(None, "--key", "-k", help="SSH private key path"),
    os_type: Optional[str] = typer.Option(None, "--os", help="Operating system (linux, freebsd, windows)"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    test_connection: bool = typer.Option(True, "--test/--no-test", help="Test connection after adding"),
):
    """Add a new managed host for shutdown operations."""
    
    try:
        console.print(f"[blue]Adding host: {hostname}")
        
        # Add host
        host = await host_manager.add_host(
            hostname=hostname,
            ip_address=ip,
            username=username,
            password=password,
            private_key_path=key_path,
            os_type=os_type,
            port=port,
        )
        
        console.print(f"[green]✓ Host added successfully: {hostname}")
        console.print(f"  ID: {host.id}")
        console.print(f"  IP: {host.ip_address}")
        console.print(f"  Connection: {host.connection_type}")
        
        # Test connection if requested
        if test_connection:
            console.print(f"\n[blue]Testing connection to {hostname}...")
            result = await host_manager.test_host_connection(hostname)
            
            if result['success']:
                console.print(f"[green]✓ Connection test successful")
                
                # Show host info if available
                if 'host_info' in result:
                    info = result['host_info']
                    console.print(f"\n[dim]Host Information:")
                    if info.get('hostname'):
                        console.print(f"  Hostname: {info['hostname']}")
                    if info.get('uname'):
                        console.print(f"  System: {info['uname']}")
                    if info.get('uptime'):
                        console.print(f"  Uptime: {info['uptime']}")
            else:
                console.print(f"[red]✗ Connection test failed: {result.get('error', 'Unknown error')}")
                console.print("[yellow]Host added but connection may need troubleshooting")
    
    except Exception as e:
        console.print(f"[red]✗ Failed to add host: {e}")
        raise typer.Exit(1)


@app.command("list")
@handle_async_command
async def list_hosts(
    connection_type: Optional[str] = typer.Option(None, "--type", help="Filter by connection type"),
    os_type: Optional[str] = typer.Option(None, "--os", help="Filter by OS type"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all managed hosts."""
    
    try:
        hosts = await host_manager.list_hosts(
            connection_type=connection_type,
            os_type=os_type,
        )
        
        if not hosts:
            console.print("[yellow]No hosts found")
            return
        
        if json_output:
            # JSON output
            host_data = []
            for host in hosts:
                host_data.append({
                    'id': host.id,
                    'hostname': host.hostname,
                    'ip_address': host.ip_address,
                    'os_type': host.os_type,
                    'connection_type': host.connection_type,
                    'credentials_ref': host.credentials_ref,
                    'discovered_at': host.discovered_at.isoformat() if host.discovered_at else None,
                })
            print(json.dumps(host_data, indent=2))
        else:
            # Table output
            table = Table(title="Managed Hosts")
            table.add_column("ID", style="cyan")
            table.add_column("Hostname", style="bold")
            table.add_column("IP Address")
            table.add_column("OS Type")
            table.add_column("Connection")
            table.add_column("Credentials")
            table.add_column("Added")
            
            for host in hosts:
                creds_status = "✓" if host.credentials_ref else "✗"
                added_date = host.discovered_at.strftime("%Y-%m-%d") if host.discovered_at else "Unknown"
                
                table.add_row(
                    str(host.id),
                    host.hostname,
                    host.ip_address or "Unknown",
                    host.os_type or "Unknown",
                    host.connection_type,
                    creds_status,
                    added_date,
                )
            
            console.print(table)
            console.print(f"\n[dim]Total hosts: {len(hosts)}")
    
    except Exception as e:
        console.print(f"[red]✗ Failed to list hosts: {e}")
        raise typer.Exit(1)


@app.command("remove")
@handle_async_command
async def remove_host(
    hostname: str = typer.Argument(..., help="Host name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove a managed host."""
    
    try:
        # Get host info first
        host = await host_manager.get_host_by_name(hostname)
        if not host:
            console.print(f"[red]✗ Host not found: {hostname}")
            raise typer.Exit(1)
        
        # Confirm removal unless forced
        if not force:
            console.print(f"[yellow]About to remove host: {hostname} ({host.ip_address})")
            if not typer.confirm("Are you sure?"):
                console.print("Cancelled")
                return
        
        # Remove host
        success = await host_manager.remove_host(hostname)
        
        if success:
            console.print(f"[green]✓ Host removed: {hostname}")
        else:
            console.print(f"[red]✗ Host not found: {hostname}")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]✗ Failed to remove host: {e}")
        raise typer.Exit(1)


@app.command("test")
@handle_async_command
async def test_connection(
    hostname: Optional[str] = typer.Argument(None, help="Host name to test (all hosts if not specified)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Test SSH connections to hosts."""
    
    try:
        if hostname:
            # Test single host
            console.print(f"[blue]Testing connection to: {hostname}")
            result = await host_manager.test_host_connection(hostname)
            
            if json_output:
                print(json.dumps(result, indent=2))
            else:
                if result['success']:
                    console.print(f"[green]✓ Connection successful")
                    if 'host_info' in result:
                        console.print("\n[dim]Host Information:")
                        for key, value in result['host_info'].items():
                            if value:
                                console.print(f"  {key}: {value}")
                else:
                    console.print(f"[red]✗ Connection failed: {result.get('error', 'Unknown error')}")
        else:
            # Test all hosts
            console.print("[blue]Testing all host connections...")
            results = await host_manager.health_check_all_hosts()
            
            if json_output:
                print(json.dumps(results, indent=2))
            else:
                console.print(f"\n[bold]Health Check Results[/bold]")
                console.print(f"Total hosts: {results['total_hosts']}")
                console.print(f"[green]Healthy: {results['healthy_hosts']}[/green]")
                console.print(f"[red]Failed: {results['failed_hosts']}[/red]")
                
                # Show detailed results
                if results['results']:
                    table = Table(title="Connection Test Results")
                    table.add_column("Hostname", style="bold")
                    table.add_column("IP Address")
                    table.add_column("Status")
                    table.add_column("Error/Info")
                    
                    for result in results['results']:
                        status = "[green]✓ OK[/green]" if result.get('success') else "[red]✗ Failed[/red]"
                        error_info = result.get('error', '')
                        if not error_info and result.get('host_info', {}).get('hostname'):
                            error_info = f"Remote: {result['host_info']['hostname']}"
                        
                        table.add_row(
                            result.get('hostname', 'Unknown'),
                            result.get('ip_address', 'Unknown'),
                            status,
                            error_info[:50] + "..." if len(error_info) > 50 else error_info,
                        )
                    
                    console.print(table)
    
    except Exception as e:
        console.print(f"[red]✗ Failed to test connections: {e}")
        raise typer.Exit(1)


@app.command("shutdown")
@handle_async_command
async def shutdown_host(
    hostname: str = typer.Argument(..., help="Host name to shutdown"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate shutdown without executing"),
    timeout: int = typer.Option(60, "--timeout", help="Command timeout in seconds"),
    command: Optional[str] = typer.Option(None, "--command", help="Custom shutdown command"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Execute shutdown command on a host."""
    
    try:
        # Confirm shutdown unless forced or dry run
        if not force and not dry_run:
            console.print(f"[red]⚠️  About to shutdown host: {hostname}")
            console.print("[yellow]This will immediately power off the remote system!")
            if not typer.confirm("Are you sure you want to continue?"):
                console.print("Cancelled")
                return
        
        if dry_run:
            console.print(f"[blue]DRY RUN: Simulating shutdown of {hostname}")
        else:
            console.print(f"[red]🔴 Executing shutdown on: {hostname}")
        
        # Execute shutdown
        result = await shutdown_executor.execute_shutdown(
            hostname=hostname,
            command=command,
            timeout=timeout,
            dry_run=dry_run,
        )
        
        # Display results
        console.print(f"\n[bold]Shutdown Result[/bold]")
        console.print(f"Host: {result.hostname}")
        console.print(f"Status: {result.status.value}")
        console.print(f"Command: {result.command}")
        console.print(f"Exit Code: {result.exit_code}")
        console.print(f"Execution Time: {result.execution_time:.2f}s")
        
        if result.stdout:
            console.print(f"Stdout: {result.stdout}")
        
        if result.stderr:
            console.print(f"[red]Stderr: {result.stderr}[/red]")
        
        if result.error_message:
            console.print(f"[red]Error: {result.error_message}[/red]")
        
        if result.success:
            if dry_run:
                console.print("[green]✓ Dry run completed successfully")
            else:
                console.print("[green]✓ Shutdown initiated successfully")
        else:
            console.print(f"[red]✗ Shutdown failed")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]✗ Failed to execute shutdown: {e}")
        raise typer.Exit(1)


@app.command("shutdown-all")
@handle_async_command
async def shutdown_all_hosts(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate shutdown without executing"),
    timeout: int = typer.Option(60, "--timeout", help="Command timeout in seconds"),
    max_concurrent: int = typer.Option(10, "--concurrent", help="Maximum concurrent shutdowns"),
    exclude: List[str] = typer.Option([], "--exclude", help="Hosts to exclude from shutdown"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Execute shutdown on all managed SSH hosts."""
    
    try:
        # Get list of hosts
        hosts = await host_manager.list_hosts(connection_type="ssh")
        hostnames = [host.hostname for host in hosts if host.hostname not in exclude]
        
        if not hostnames:
            console.print("[yellow]No hosts found for shutdown")
            return
        
        # Show what will be shut down
        console.print(f"[blue]Hosts to shutdown ({len(hostnames)}):")
        for hostname in hostnames:
            console.print(f"  • {hostname}")
        
        if exclude:
            console.print(f"\n[dim]Excluded hosts: {', '.join(exclude)}")
        
        # Confirm shutdown unless forced or dry run
        if not force and not dry_run:
            console.print(f"\n[red]⚠️  About to shutdown {len(hostnames)} hosts!")
            console.print("[yellow]This will immediately power off all remote systems!")
            if not typer.confirm("Are you sure you want to continue?"):
                console.print("Cancelled")
                return
        
        if dry_run:
            console.print(f"\n[blue]DRY RUN: Simulating mass shutdown")
        else:
            console.print(f"\n[red]🔴 Executing mass shutdown...")
        
        # Execute mass shutdown
        results = await shutdown_executor.execute_mass_shutdown(
            hostnames=hostnames,
            timeout=timeout,
            max_concurrent=max_concurrent,
            dry_run=dry_run,
        )
        
        # Display results summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        console.print(f"\n[bold]Mass Shutdown Results[/bold]")
        console.print(f"Total hosts: {len(results)}")
        console.print(f"[green]Successful: {successful}[/green]")
        console.print(f"[red]Failed: {failed}[/red]")
        
        # Detailed results table
        table = Table(title="Detailed Results")
        table.add_column("Hostname", style="bold")
        table.add_column("Status")
        table.add_column("Exit Code")
        table.add_column("Time (s)")
        table.add_column("Error")
        
        for result in results:
            status_text = "[green]✓ Success[/green]" if result.success else "[red]✗ Failed[/red]"
            error_text = result.error_message or ""
            
            table.add_row(
                result.hostname,
                status_text,
                str(result.exit_code) if result.exit_code is not None else "N/A",
                f"{result.execution_time:.1f}" if result.execution_time else "N/A",
                error_text[:30] + "..." if len(error_text) > 30 else error_text,
            )
        
        console.print(table)
        
        if failed > 0:
            console.print(f"\n[red]⚠️  {failed} hosts failed to shutdown")
            raise typer.Exit(1)
        else:
            if dry_run:
                console.print("\n[green]✓ Mass shutdown simulation completed successfully")
            else:
                console.print("\n[green]✓ Mass shutdown completed successfully")
    
    except Exception as e:
        console.print(f"[red]✗ Failed to execute mass shutdown: {e}")
        raise typer.Exit(1)


@app.command("discover")
@handle_async_command
async def discover_hosts(
    network: str = typer.Argument(..., help="Network to scan (e.g., 192.168.1.0/24)"),
    add_discovered: bool = typer.Option(False, "--add", help="Automatically add discovered hosts"),
    username: str = typer.Option("root", "--user", help="Username for discovery"),
    timeout: int = typer.Option(5, "--timeout", help="Connection timeout"),
    max_concurrent: int = typer.Option(50, "--concurrent", help="Maximum concurrent scans"),
):
    """Discover SSH-accessible hosts on the network."""
    
    try:
        discovery = HostDiscovery(host_manager)
        
        console.print(f"[blue]Discovering hosts on network: {network}")
        console.print(f"Username: {username}, Timeout: {timeout}s")
        
        # Start discovery
        discovered = await discovery.auto_discover(
            network=network,
            add_discovered=add_discovered,
            username=username,
        )
        
        if not discovered:
            console.print("[yellow]No accessible hosts discovered")
            return
        
        console.print(f"\n[green]✓ Discovered {len(discovered)} accessible hosts")
        
        # Show results
        table = Table(title="Discovered Hosts")
        table.add_column("IP Address", style="cyan")
        table.add_column("Username")
        table.add_column("Key Path")
        table.add_column("Hostname")
        table.add_column("System")
        table.add_column("Added")
        
        for host_info in discovered:
            hostname = host_info.get('host_info', {}).get('hostname', 'Unknown')
            system_info = host_info.get('host_info', {}).get('uname', 'Unknown')
            added_status = "✓" if add_discovered else "No"
            
            table.add_row(
                host_info['ip_address'],
                host_info['username'],
                host_info.get('key_path', 'N/A'),
                hostname,
                system_info[:30] + "..." if len(system_info) > 30 else system_info,
                added_status,
            )
        
        console.print(table)
        
        if add_discovered:
            console.print(f"\n[green]✓ {len(discovered)} hosts added to management")
        else:
            console.print(f"\n[dim]Use --add to automatically add discovered hosts")
    
    except Exception as e:
        console.print(f"[red]✗ Discovery failed: {e}")
        raise typer.Exit(1)


@app.command("triggers")
@handle_async_command
async def manage_triggers(
    action: str = typer.Argument(..., help="Action: list, add, remove, start, stop"),
    condition: Optional[str] = typer.Option(None, help="Trigger condition (onbattery, lowbattery)"),
    target_hosts: Optional[List[str]] = typer.Option([], "--target", help="Target hosts for shutdown"),
    immediate: bool = typer.Option(True, "--immediate/--delayed", help="Immediate vs delayed trigger"),
    delay: float = typer.Option(0.0, "--delay", help="Delay in seconds for delayed triggers"),
):
    """Manage shutdown triggers for UPS events."""
    
    try:
        if action == "list":
            # List current triggers
            status = trigger_manager.get_trigger_status()
            
            if not status:
                console.print("[yellow]No triggers configured")
                return
            
            table = Table(title="Shutdown Triggers")
            table.add_column("Condition", style="bold")
            table.add_column("Enabled")
            table.add_column("Active")
            table.add_column("Mode")
            table.add_column("Targets")
            table.add_column("Triggered At")
            
            for trigger_status in status:
                enabled_text = "[green]✓[/green]" if trigger_status['enabled'] else "[red]✗[/red]"
                active_text = "[red]🔴[/red]" if trigger_status['active'] else "[dim]○[/dim]"
                mode_text = "Immediate" if trigger_status['immediate'] else f"Delayed ({trigger_status['delay_seconds']}s)"
                triggered_text = trigger_status['triggered_at'] or "Never"
                
                table.add_row(
                    trigger_status['condition'],
                    enabled_text,
                    active_text,
                    mode_text,
                    str(trigger_status['target_hosts']),
                    triggered_text,
                )
            
            console.print(table)
        
        elif action == "add":
            if not condition:
                console.print("[red]✗ Condition required for adding trigger")
                raise typer.Exit(1)
            
            # Create trigger based on condition
            if condition.lower() in ["onbattery", "ob"]:
                trigger = trigger_manager.create_immediate_onbattery_trigger(
                    target_hosts=target_hosts if target_hosts else None,
                )
                trigger_manager.add_trigger(trigger)
                console.print(f"[green]✓ Added OnBattery trigger for {target_hosts or ['srv-pbs-01']}")
            else:
                console.print(f"[red]✗ Unsupported condition: {condition}")
                raise typer.Exit(1)
        
        elif action == "remove":
            if not condition:
                console.print("[red]✗ Condition required for removing trigger")
                raise typer.Exit(1)
            
            condition_map = {
                "onbattery": TriggerCondition.ON_BATTERY,
                "ob": TriggerCondition.ON_BATTERY,
                "lowbattery": TriggerCondition.LOW_BATTERY,
                "lb": TriggerCondition.LOW_BATTERY,
            }
            
            trigger_condition = condition_map.get(condition.lower())
            if not trigger_condition:
                console.print(f"[red]✗ Unknown condition: {condition}")
                raise typer.Exit(1)
            
            removed = trigger_manager.remove_trigger(trigger_condition)
            if removed:
                console.print(f"[green]✓ Removed {condition} trigger")
            else:
                console.print(f"[yellow]No {condition} trigger found")
        
        elif action == "start":
            console.print("[blue]Starting trigger monitoring...")
            await trigger_manager.start_monitoring(interval=5.0)
            console.print("[green]✓ Trigger monitoring started")
            console.print("[dim]Press Ctrl+C to stop monitoring")
            
            try:
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[blue]Stopping trigger monitoring...")
                await trigger_manager.stop_monitoring()
                console.print("[green]✓ Trigger monitoring stopped")
        
        elif action == "stop":
            await trigger_manager.stop_monitoring()
            console.print("[green]✓ Trigger monitoring stopped")
        
        else:
            console.print(f"[red]✗ Unknown action: {action}")
            console.print("Available actions: list, add, remove, start, stop")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]✗ Trigger management failed: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()