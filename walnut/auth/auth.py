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
