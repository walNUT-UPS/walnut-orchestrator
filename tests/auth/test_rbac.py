import pytest
from httpx import AsyncClient
from contextlib import asynccontextmanager

from walnut.auth.models import Role
from walnut.auth.schemas import UserCreate

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def get_test_user_manager():
    from walnut.auth.deps import get_user_manager, get_user_db
    from walnut.database.connection import get_db_session

    async for session in get_db_session():
        async for user_db in get_user_db(session):
            async for um in get_user_manager(user_db):
                yield um


async def test_viewer_cannot_access_admin_route(async_client: AsyncClient):
    # Register and login as a viewer
    await async_client.post(
        "/auth", json={"email": "viewer@example.com", "password": "password"}
    )
    await async_client.post(
        "/auth/jwt/login",
        data={"username": "viewer@example.com", "password": "password"},
    )

    # Try to access the admin-only route
    response = await async_client.get("/api/admin-only")
    assert response.status_code == 403


async def test_admin_can_access_admin_route(async_client: AsyncClient):
    # Create an admin user directly in the database
    async with get_test_user_manager() as user_manager:
        user_create = UserCreate(email="admin@example.com", password="password")
        user = await user_manager.create(user_create, safe=True)
        user.role = Role.ADMIN
        user.is_superuser = True
        await user_manager.user_db.update(user)

    # Login as the admin user
    await async_client.post(
        "/auth/jwt/login",
        data={"username": "admin@example.com", "password": "password"},
    )

    # Access the admin-only route
    response = await async_client.get("/api/admin-only")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome, admin admin@example.com!"}
