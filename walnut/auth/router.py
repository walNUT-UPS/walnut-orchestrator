from fastapi import APIRouter, Depends

from walnut.auth.auth import auth_backend
from walnut.auth.deps import (
    current_active_user,
    current_admin,
    fastapi_users,
)
from walnut.auth.models import User
from walnut.auth.schemas import MeResponse, UserCreate, UserRead, UserUpdate
from walnut.config import settings

# APIRouter for all authentication-related endpoints
auth_router = APIRouter(dependencies=[Depends(csrf_protect)])

# Mount the login/logout router
auth_router.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/jwt", tags=["Auth"]
)

# Conditionally mount the registration router
if settings.SIGNUP_ENABLED:
    auth_router.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="",
        tags=["Auth"],
    )

# Mount other fastapi-users routers (password reset, verification)
auth_router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="",
    tags=["Auth"],
)
auth_router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="",
    tags=["Auth"],
)

# Router for user management and API endpoints
api_router = APIRouter()

# Mount the users router from fastapi-users
api_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["Users"],
)

# /api/me endpoint
@api_router.get("/me", response_model=MeResponse, tags=["Users"])
async def me(user: User = Depends(current_active_user)):
    """
    Get current user details.
    """
    return user

# Example admin-only endpoint for testing RBAC
@api_router.get("/admin-only", tags=["Admin"])
async def admin_only_endpoint(user: User = Depends(current_admin)):
    """
    An example endpoint that only admin users can access.
    """
    return {"message": f"Welcome, admin {user.email}!"}
