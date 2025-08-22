from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from walnut.config import settings

cookie_transport = CookieTransport(
    cookie_name=settings.COOKIE_NAME_ACCESS,
    cookie_max_age=int(settings.ACCESS_TTL.total_seconds()),
    cookie_secure=settings.SECURE_COOKIES,
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.JWT_SECRET,
        lifetime_seconds=int(settings.ACCESS_TTL.total_seconds()),
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

auth_backends = [auth_backend]

# OIDC client and backend - initialized lazily when needed
oidc_client = None
oauth_backend = None

def get_oidc_client():
    """Get OIDC client, initializing it if needed."""
    global oidc_client
    if settings.OIDC_ENABLED and oidc_client is None:
        from httpx_oauth.clients.openid import OpenID
        oidc_client = OpenID(
            client_id=settings.OIDC_CLIENT_ID,
            client_secret=settings.OIDC_CLIENT_SECRET,
            openid_configuration_endpoint=settings.OIDC_DISCOVERY_URL,
            name="oidc",
        )
    return oidc_client

if settings.OIDC_ENABLED:
    oauth_backend = AuthenticationBackend(
        name="oidc",
        transport=cookie_transport,
        get_strategy=get_jwt_strategy,
    )
    auth_backends.append(oauth_backend)
