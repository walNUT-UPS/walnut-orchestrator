import pytest
import respx
from httpx import Response
from sqlalchemy import select
from walnut.auth.models import OAuthAccount, User
from walnut.database.engine import SessionLocal
import anyio

# The base URL of the mocked OIDC provider
OIDC_PROVIDER_URL = "https://example.com"
AUTHORIZATION_URL = f"{OIDC_PROVIDER_URL}/auth"
TOKEN_URL = f"{OIDC_PROVIDER_URL}/token"
USERINFO_URL = f"{OIDC_PROVIDER_URL}/userinfo"

def get_user_from_db(email: str) -> User | None:
    with SessionLocal() as session:
        return session.query(User).filter_by(email=email).first()

def get_oauth_account_from_db(user_id: str) -> OAuthAccount | None:
    with SessionLocal() as session:
        return session.query(OAuthAccount).filter_by(user_id=user_id).first()

@pytest.mark.asyncio
@respx.mock
async def test_oidc_full_flow_new_user(oidc_async_client):
    """
    Test the full OIDC login flow for a brand new user.
    """
    # The discovery endpoint is mocked globally in the oidc_async_client fixture.

    # Test the authorization redirect
    authorize_response = await oidc_async_client.get("/auth/oauth/oidc/authorize", follow_redirects=False)
    assert authorize_response.status_code == 302
    assert authorize_response.headers["location"].startswith(AUTHORIZATION_URL)

    # Mock the token and userinfo endpoints
    respx.post(TOKEN_URL).mock(return_value=Response(200, json={"access_token": "test_access_token"}))
    user_email = "new.user@example.com"
    respx.get(USERINFO_URL).mock(return_value=Response(200, json={"email": user_email, "roles": ["admin"]}))

    # Simulate the callback from the OIDC provider
    callback_url = f"/auth/oauth/oidc/callback?code=test_code&state=test_state"
    callback_response = await oidc_async_client.get(callback_url, follow_redirects=False)

    assert callback_response.status_code == 307
    assert callback_response.headers["location"] == "/"

    # Verify the user was created in the database
    user = await anyio.to_thread.run_sync(get_user_from_db, user_email)
    assert user is not None
    assert user.email == user_email
    assert user.role == "admin"

    oauth_account = await anyio.to_thread.run_sync(get_oauth_account_from_db, user.id)
    assert oauth_account is not None
    assert oauth_account.oauth_name == "oidc"

@pytest.mark.asyncio
@respx.mock
async def test_oidc_full_flow_existing_user(oidc_async_client):
    """
    Test the OIDC login flow for an existing user.
    """
    existing_email = "existing.user@example.com"

    def create_existing_user():
        with SessionLocal() as session:
            user = User(email=existing_email, role="viewer", is_active=True, is_verified=True, hashed_password="dummy")
            session.add(user)
            session.commit()
    await anyio.to_thread.run_sync(create_existing_user)

    # Mock the token and userinfo endpoints
    respx.post(TOKEN_URL).mock(return_value=Response(200, json={"access_token": "test_access_token"}))
    respx.get(USERINFO_URL).mock(return_value=Response(200, json={"email": existing_email, "roles": ["admin"]}))

    # Simulate authorization and callback
    await oidc_async_client.get("/auth/oauth/oidc/authorize", follow_redirects=False)
    callback_response = await oidc_async_client.get("/auth/oauth/oidc/callback?code=test_code&state=test_state", follow_redirects=False)

    assert callback_response.status_code == 307

    # Verify the user's role was updated and OAuthAccount was linked
    user = await anyio.to_thread.run_sync(get_user_from_db, existing_email)
    assert user is not None
    assert user.role == "admin"

    oauth_account = await anyio.to_thread.run_sync(get_oauth_account_from_db, user.id)
    assert oauth_account is not None