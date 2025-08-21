import enum
from datetime import datetime
from typing import List
import uuid

from fastapi_users.db import (
    SQLAlchemyBaseUserTableUUID,
    SQLAlchemyBaseOAuthAccountTableUUID,
)
from sqlalchemy import Column, DateTime, Enum, func, ForeignKey, UUID
from sqlalchemy.orm import relationship, Mapped

from walnut.database.models import Base


class Role(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    __tablename__ = "oauth_accounts"
    user_id: Mapped[uuid.UUID] = Column(UUID, ForeignKey("users.id", ondelete="cascade"), nullable=False)


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    role: Mapped[Role] = Column(Enum(Role), default=Role.VIEWER, nullable=False)
    created_at: Mapped[datetime] = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    oauth_accounts: Mapped[List[OAuthAccount]] = relationship("OAuthAccount", lazy="joined")
