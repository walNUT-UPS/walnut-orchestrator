import uuid
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from jose import jwt, JWTError
import anyio
from sqlalchemy import select

from walnut.auth.sync_user_db import SyncSQLAlchemyUserDatabase
from walnut.auth.auth import auth_backends
from walnut.auth.models import Role, User, OAuthAccount as OAuthAccountModel
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

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_details: dict,
        request: Optional[Request] = None,
    ) -> User:
        # This is a bit of a dance because fastapi-users is async, but our DB session is sync.
        # We need to use run_sync_in_worker_thread to avoid blocking the event loop.
        import anyio

        user = await super().oauth_callback(
            oauth_name, access_token, account_details, request
        )

        # Map OIDC roles to application roles
        oidc_roles = account_details.get("roles", [])

        # Check for admin roles first
        is_admin = any(
            admin_role in oidc_roles for admin_role in settings.OIDC_ADMIN_ROLES
        )
        if is_admin:
            user.role = Role.ADMIN
        else:
            # Check for viewer roles if not an admin
            is_viewer = any(
                viewer_role in oidc_roles for viewer_role in settings.OIDC_VIEWER_ROLES
            )
            if is_viewer:
                user.role = Role.VIEWER
            # If no roles match, the user will have the default role (viewer)

        def sync_db_operations(session, user_to_update):
            session.add(user_to_update)
            session.commit()
            session.refresh(user_to_update)
            return user_to_update

        user = await anyio.to_thread.run_sync(sync_db_operations, self.user_db.session, user)

        return user


def get_user_db():
    with get_db_session() as session:
        yield SyncSQLAlchemyUserDatabase(session, User, OAuthAccountModel)


def get_user_manager(
    user_db: SyncSQLAlchemyUserDatabase = Depends(get_user_db),
):
    return UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    auth_backends,
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


# Lightweight, sync-safe auth dependency for endpoints sensitive to async/sync DB mixups
async def require_current_user(request: Request) -> User:
    """
    Validates the JWT from cookie or Authorization header and returns the active user.

    Bypasses fastapi-users' dependency stack to avoid async/sync DB mismatches
    when using a sync SQLAlchemy session.
    """
    token = None
    # Prefer cookie from our configured cookie name
    try:
        token = request.cookies.get(settings.COOKIE_NAME_ACCESS)
    except Exception:
        token = None
    # Fallback to Bearer token
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            audience="fastapi-users:auth",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Load user using sync session wrapped with anyio
    async with get_db_session() as session:
        result = await anyio.to_thread.run_sync(session.execute, select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
        return user
