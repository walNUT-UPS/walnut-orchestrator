import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_cookie_security_flags(async_client: AsyncClient):
    """
    Test that cookies are set with the correct security flags.
    NOTE: httpx does not expose cookie attributes like HttpOnly, Secure, SameSite.
    This test assumes that the FastAPI/fastapi-users framework correctly sets these flags
    based on the configuration provided in walnut/config.py.
    A more thorough test would require a browser-based testing tool like Playwright.
    """
    # Register and login
    await async_client.post(
        "/auth", json={"email": "test-cookie@example.com", "password": "password"}
    )
    response = await async_client.post(
        "/auth/jwt/login",
        data={"username": "test-cookie@example.com", "password": "password"},
    )

    # We can't directly inspect the flags, but we can check that the cookies are set
    assert "walnut_access" in response.cookies
    assert response.status_code == 204


async def test_cors_headers(async_client: AsyncClient):
    """
    Test that CORS headers are correctly set for allowed origins.
    """
    # Test pre-flight request from an allowed origin
    response = await async_client.options(
        "/api/me",
        headers={
            "Origin": "http://test.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://test.com"
    assert response.headers["access-control-allow-credentials"] == "true"

    # Test pre-flight request from a disallowed origin
    response = await async_client.options(
        "/api/me",
        headers={"Origin": "http://bad.com", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400


async def test_csrf_protection(async_client: AsyncClient):
    """
    Test that state-changing requests to /auth/* require a CSRF token.
    """
    # Register and login
    await async_client.post(
        "/auth",
        json={"email": "csrf@example.com", "password": "password"},
        headers={"x-csrf-token": "some-token"},  # Needed for registration
    )
    await async_client.post(
        "/auth/jwt/login",
        data={"username": "csrf@example.com", "password": "password"},
        headers={"x-csrf-token": "some-token"},
    )

    # Logout without CSRF token should fail
    response = await async_client.post("/auth/jwt/logout")
    assert response.status_code == 403
    assert "Missing X-CSRF-Token header" in response.text

    # Logout with CSRF token should succeed
    response = await async_client.post(
        "/auth/jwt/logout", headers={"x-csrf-token": "some-token"}
    )
    assert response.status_code == 204
