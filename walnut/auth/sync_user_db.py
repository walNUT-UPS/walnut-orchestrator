"""
Sync SQLAlchemy User Database adapter for fastapi-users.

This module provides a sync version of SQLAlchemyUserDatabase 
that works with sync SQLAlchemy sessions instead of async ones.
"""
from typing import Optional, Dict, Any, Generic, TypeVar
import uuid

from fastapi_users.db import BaseUserDatabase
from fastapi_users.models import UP, ID
from sqlalchemy import select
from sqlalchemy.orm import Session

from walnut.auth.models import User

class SyncSQLAlchemyUserDatabase(BaseUserDatabase[User, uuid.UUID], Generic[UP, ID]):
    """
    Database adapter for sync SQLAlchemy.
    
    This is a sync version of fastapi-users' SQLAlchemyUserDatabase
    that works with sync SQLAlchemy sessions.
    """
    
    def __init__(self, session: Session, user_table: type[UP]):
        self.session = session
        self.user_table = user_table
    
    async def get(self, id: ID) -> Optional[UP]:
        """Get user by ID."""
        statement = select(self.user_table).where(self.user_table.id == id)
        result = self.session.execute(statement)
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[UP]:
        """Get user by email."""
        statement = select(self.user_table).where(self.user_table.email == email)
        result = self.session.execute(statement)
        return result.scalar_one_or_none()
    
    async def get_by_oauth_account(self, oauth: str, account_id: str) -> Optional[UP]:
        """Get user by OAuth account - not implemented for basic auth."""
        raise NotImplementedError("OAuth not implemented in this sync adapter")
    
    async def create(self, create_dict: Dict[str, Any]) -> UP:
        """Create a new user."""
        user = self.user_table(**create_dict)
        self.session.add(user)
        self.session.flush()  # Get the ID
        return user
    
    async def update(self, user: UP, update_dict: Dict[str, Any]) -> UP:
        """Update an existing user."""
        for key, value in update_dict.items():
            if hasattr(user, key):
                setattr(user, key, value)
        self.session.flush()
        return user
    
    async def delete(self, user: UP) -> None:
        """Delete a user."""
        self.session.delete(user)
        self.session.flush()