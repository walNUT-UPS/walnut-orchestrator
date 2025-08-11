import uuid
import logging

from fastapi import Depends, HTTPException, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase

from walnut.auth.auth import auth_backend
from walnut.auth.models import Role, User
from walnut.config import settings
from walnut.database.connection import get_db_session


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.JWT_SECRET
    verification_token_secret = settings.JWT_SECRET

    async def on_after_register(self, user: User, request=None):
        """Called after a user has registered."""
        logging.info(f"User {user.id} has registered.")

    async def on_after_forgot_password(self, user: User, token: str, request=None):
        """Called after a user has requested a password reset."""
        logging.info(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(self, user: User, token: str, request=None):
        """Called after a user has requested verification."""
        logging.info(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_db():
    async with get_db_session() as session:  # this yields a sync Session
        yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)
current_user = fastapi_users.current_user()


def current_admin(user: User = Depends(current_active_user)):
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted",
        )
    return user
