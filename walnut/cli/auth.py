"""
Authentication and user management CLI commands for walNUT.
"""

import asyncio
import json

import click
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from walnut.auth.deps import get_user_manager
from walnut.auth.models import Role, User
from fastapi_users.db import SQLAlchemyUserDatabase
from walnut.database.connection import close_database, init_database
from walnut.cli.utils import handle_async_command

console = Console()


@click.group(name="auth")
def auth_cli():
    """walNUT Authentication and User Management Commands"""
    pass


@auth_cli.command()
@click.option("--email", required=True, help="Email of the admin user.")
@click.option("--password", required=True, prompt=True, hide_input=True, help="Password of the admin user.")
@handle_async_command
async def create_admin(email, password):
    """Create a new admin user."""
    console.print(f"[bold blue]Creating admin user: {email}[/bold blue]")
    await init_database(create_tables=False)
    try:
        from walnut.database.connection import get_connection_manager
        from walnut.auth.deps import UserManager
        from fastapi_users.exceptions import UserAlreadyExists
        from walnut.auth.schemas import UserCreate
        
        manager = await get_connection_manager()
        async with manager.get_session() as session:
            user_db = SQLAlchemyUserDatabase(session, User)
            user_manager = UserManager(user_db)
            
            try:
                user_create = UserCreate(email=email, password=password)
                user = await user_manager.create(user_create, safe=True)
                
                # Update user to admin role
                update_dict = {"role": Role.ADMIN, "is_superuser": True}
                user = await user_manager.user_db.update(user, update_dict)
                await session.commit()
                console.print(f"[green]✅ Admin user {user.email} created successfully![/green]")
            except UserAlreadyExists:
                console.print(f"[red]User with email {email} already exists.[/red]")
    finally:
        await close_database()


@auth_cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format.")
@handle_async_command
async def list_users(json_output):
    """List all users."""
    await init_database(create_tables=False)
    try:
        from walnut.database.connection import get_connection_manager
        from walnut.auth.deps import UserManager
        
        manager = await get_connection_manager()
        async with manager.get_session() as session:
            user_db = SQLAlchemyUserDatabase(session, User)
            user_manager = UserManager(user_db)
            
            # Get all users - need to implement this method
            from sqlalchemy import select
            result = await session.execute(select(User))
            users = result.scalars().all()
            
            if json_output:
                user_dicts = []
                for user in users:
                    user_dict = {
                        "id": str(user.id),
                        "email": user.email,
                        "role": user.role.value,
                        "is_active": user.is_active,
                        "is_verified": user.is_verified,
                        "is_superuser": user.is_superuser,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    }
                    user_dicts.append(user_dict)
                console.print(JSON(json.dumps(user_dicts, default=str)))
            else:
                table = Table(title="walNUT Users")
                table.add_column("ID", style="cyan")
                table.add_column("Email", style="magenta")
                table.add_column("Role", style="yellow")
                table.add_column("Active", style="green")
                table.add_column("Verified", style="blue")
                for user in users:
                    table.add_row(
                        str(user.id),
                        user.email,
                        user.role.value,
                        "✅" if user.is_active else "❌",
                        "✅" if user.is_verified else "❌",
                    )
                console.print(table)
    finally:
        await close_database()


@auth_cli.command()
@click.argument("email")
@click.option("--role", type=click.Choice([r.value for r in Role]), required=True)
@handle_async_command
async def set_role(email, role):
    """Set the role for a user."""
    await init_database(create_tables=False)
    try:
        async for user_manager in get_user_manager():
            user = await user_manager.get_by_email(email)
            if not user:
                console.print(f"[red]User with email {email} not found.[/red]")
                return
            user.role = Role(role)
            if role == Role.ADMIN.value:
                user.is_superuser = True
            else:
                user.is_superuser = False
            await user_manager.user_db.update(user)
            console.print(f"[green]✅ Role for {email} set to {role}[/green]")
    finally:
        await close_database()


@auth_cli.command()
@click.argument("email")
@handle_async_command
async def disable(email):
    """Disable a user."""
    await init_database(create_tables=False)
    try:
        async for user_manager in get_user_manager():
            user = await user_manager.get_by_email(email)
            if not user:
                console.print(f"[red]User with email {email} not found.[/red]")
                return
            user.is_active = False
            await user_manager.user_db.update(user)
            console.print(f"[green]✅ User {email} disabled.[/green]")
    finally:
        await close_database()


@auth_cli.command()
@click.argument("email")
@handle_async_command
async def enable(email):
    """Enable a user."""
    await init_database(create_tables=False)
    try:
        async for user_manager in get_user_manager():
            user = await user_manager.get_by_email(email)
            if not user:
                console.print(f"[red]User with email {email} not found.[/red]")
                return
            user.is_active = True
            await user_manager.user_db.update(user)
            console.print(f"[green]✅ User {email} enabled.[/green]")
    finally:
        await close_database()


@auth_cli.command()
@click.argument("email")
@click.option("--password", required=True, prompt=True, hide_input=True)
@handle_async_command
async def reset_password(email, password):
    """Reset a user's password."""
    await init_database(create_tables=False)
    try:
        async for user_manager in get_user_manager():
            user = await user_manager.get_by_email(email)
            if not user:
                console.print(f"[red]User with email {email} not found.[/red]")
                return
            user.hashed_password = user_manager.password_helper.hash(password)
            await user_manager.user_db.update(user)
            console.print(f"[green]✅ Password for {email} reset.[/green]")
    finally:
        await close_database()
