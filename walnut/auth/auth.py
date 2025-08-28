from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from walnut.config import settings
from walnut.core.app_settings import get_setting

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
    """Get OIDC client, initializing it if needed.

    Falls back to app settings store when environment variables are not set.
    """
    global oidc_client
    if oidc_client is not None:
        return oidc_client

    # Read environment-first, then app settings
    cfg = get_setting("oidc_config") or {}
    enabled = bool(settings.OIDC_ENABLED or cfg.get("enabled"))
    if not enabled:
        return None

    client_id = settings.OIDC_CLIENT_ID or cfg.get("client_id")
    client_secret = settings.OIDC_CLIENT_SECRET or cfg.get("client_secret")
    discovery = settings.OIDC_DISCOVERY_URL or cfg.get("discovery_url")

    if not client_id or not client_secret or not discovery:
        # Insufficient configuration — do not initialize to avoid broken routes
        return None

    from httpx_oauth.clients.openid import OpenID
    oidc_client = OpenID(
        client_id=client_id,
        client_secret=client_secret,
        openid_configuration_endpoint=discovery,
        name="oidc",
    )
    return oidc_client

from walnut.core.app_settings import get_setting as _get_setting_for_router
_cfg = _get_setting_for_router("oidc_config") or {}
_enabled = bool(settings.OIDC_ENABLED or _cfg.get("enabled"))
if _enabled and get_oidc_client() is not None:
    oauth_backend = AuthenticationBackend(
        name="oidc",
        transport=cookie_transport,
        get_strategy=get_jwt_strategy,
    )
    auth_backends.append(oauth_backend)
