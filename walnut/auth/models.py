import enum
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Column, DateTime, Enum, func

from walnut.database.models import Base


class Role(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    role: Role = Column(Enum(Role), default=Role.VIEWER, nullable=False)
    created_at: datetime = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at: datetime = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
