import uuid
from fastapi_users import schemas
from pydantic import BaseModel, EmailStr
from walnut.auth.models import Role


class UserRead(schemas.BaseUser[uuid.UUID]):
    role: Role


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    role: Role | None = None


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
