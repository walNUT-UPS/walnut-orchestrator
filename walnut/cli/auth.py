"""
Authentication and user management CLI commands for walNUT.
"""

import json
import anyio
import click
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from walnut.auth.models import Role, User
from walnut.auth.schemas import UserCreate
from walnut.database.engine import SessionLocal
from fastapi_users.db import SQLAlchemyUserDatabase
from walnut.auth.deps import UserManager
from fastapi_users.exceptions import UserAlreadyExists

console = Console()


@click.group(name="auth")
def auth_cli():
    """walNUT Authentication and User Management Commands"""
    pass


@auth_cli.command()
@click.option("--email", required=True, help="Email of the admin user.")
@click.option("--password", required=True, prompt=True, hide_input=True, help="Password of the admin user.")
def create_admin(email, password):
    """Create a new admin user."""
    console.print(f"[bold blue]Creating admin user: {email}[/bold blue]")
    session = SessionLocal()
    try:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        # The user manager's create method is async, so we need to run it in a thread.
        user_create = UserCreate(email=email, password=password)

        user = anyio.run(user_manager.create, user_create, True)
        
        # Update user to admin role
        update_dict = {"role": Role.ADMIN, "is_superuser": True}

        user = anyio.run(user_manager.user_db.update, user, update_dict)
        session.commit()
        console.print(f"[green]✅ Admin user {user.email} created successfully![/green]")
    except UserAlreadyExists:
        console.print(f"[red]User with email {email} already exists.[/red]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")
        session.rollback()
    finally:
        session.close()


@auth_cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format.")
def list_users(json_output):
    """List all users."""
    session = SessionLocal()
    try:
        from sqlalchemy import select
        users = session.execute(select(User)).scalars().all()
        
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
        session.close()


@auth_cli.command()
@click.argument("email")
@click.option("--role", type=click.Choice([r.value for r in Role]), required=True)
def set_role(email, role):
    """Set the role for a user."""
    session = SessionLocal()
    try:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        user = anyio.run(user_manager.get_by_email, email)

        if not user:
            console.print(f"[red]User with email {email} not found.[/red]")
            return

        user.role = Role(role)
        if role == Role.ADMIN.value:
            user.is_superuser = True
        else:
            user.is_superuser = False

        anyio.run(user_manager.user_db.update, user)
        session.commit()
        console.print(f"[green]✅ Role for {email} set to {role}[/green]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")
        session.rollback()
    finally:
        session.close()


@auth_cli.command()
@click.argument("email")
def disable(email):
    """Disable a user."""
    session = SessionLocal()
    try:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        user = anyio.run(user_manager.get_by_email, email)

        if not user:
            console.print(f"[red]User with email {email} not found.[/red]")
            return

        user.is_active = False

        anyio.run(user_manager.user_db.update, user)
        session.commit()
        console.print(f"[green]✅ User {email} disabled.[/green]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")
        session.rollback()
    finally:
        session.close()


@auth_cli.command()
@click.argument("email")
def enable(email):
    """Enable a user."""
    session = SessionLocal()
    try:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        user = anyio.run(user_manager.get_by_email, email)

        if not user:
            console.print(f"[red]User with email {email} not found.[/red]")
            return

        user.is_active = True

        anyio.run(user_manager.user_db.update, user)
        session.commit()
        console.print(f"[green]✅ User {email} enabled.[/green]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")
        session.rollback()
    finally:
        session.close()


@auth_cli.command()
@click.argument("email")
@click.option("--password", required=True, prompt=True, hide_input=True)
def reset_password(email, password):
    """Reset a user's password."""
    session = SessionLocal()
    try:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        user = anyio.run(user_manager.get_by_email, email)

        if not user:
            console.print(f"[red]User with email {email} not found.[/red]")
            return

        user.hashed_password = user_manager.password_helper.hash(password)

        anyio.run(user_manager.user_db.update, user)
        session.commit()
        console.print(f"[green]✅ Password for {email} reset.[/green]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")
        session.rollback()
    finally:
        session.close()
