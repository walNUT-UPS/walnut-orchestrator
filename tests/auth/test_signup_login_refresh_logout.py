import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register(async_client: AsyncClient):
    response = await async_client.post(
        "/auth",
        json={"email": "test@example.com", "password": "password"},
    )
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "test@example.com"
    assert user["is_active"] is True
    assert "role" in user
    assert user["role"] == "viewer"


async def test_login_and_me(async_client: AsyncClient):
    # Register a new user
    await async_client.post(
        "/auth",
        json={"email": "test2@example.com", "password": "password"},
    )

    # Login
    response = await async_client.post(
        "/auth/jwt/login",
        data={"username": "test2@example.com", "password": "password"},
    )
    assert response.status_code == 204
    assert "walnut_access" in response.cookies

    # Access /api/me
    response = await async_client.get("/api/me")
    assert response.status_code == 200
    user = response.json()
    assert user["email"] == "test2@example.com"
    assert user["role"] == "viewer"


async def test_logout(async_client: AsyncClient):
    # Register and login
    await async_client.post(
        "/auth",
        json={"email": "test3@example.com", "password": "password"},
    )
    await async_client.post(
        "/auth/jwt/login",
        data={"username": "test3@example.com", "password": "password"},
    )

    # Logout
    response = await async_client.post("/auth/jwt/logout")
    assert response.status_code == 204
    # httpx does not expose response cookies that have been cleared
    # so we can't check for "walnut_access" not in response.cookies
    # instead, we check that we are logged out by accessing a protected route

    # /api/me should now be unauthorized
    response = await async_client.get("/api/me")
    assert response.status_code == 401
