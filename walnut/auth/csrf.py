from fastapi import Request, HTTPException, status
from walnut.config import settings


async def csrf_protect(request: Request):
    """
    A dependency that provides CSRF protection by checking for the
    X-CSRF-Token header on all state-changing requests.
    
    Note: This dependency is WebSocket-aware and will skip CSRF checks
    for WebSocket connections.
    """
    # Skip CSRF protection entirely in testing mode
    if getattr(settings, "TESTING_MODE", False):
        return

    # Skip CSRF protection for WebSocket connections
    # WebSocket connections don't have traditional HTTP methods
    if not hasattr(request, 'method'):
        return
    
    # Additional check: WebSocket requests may have a different scope type
    if hasattr(request, 'scope') and request.scope.get('type') == 'websocket':
        return
        
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Allow Bearer token usage to bypass CSRF (no cookies involved)
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return

        header_name = getattr(settings, "CSRF_HEADER_NAME", "x-csrf-token")
        cookie_name = getattr(settings, "CSRF_COOKIE_NAME", "walnut_csrf")

        header_token = request.headers.get(header_name)
        if not header_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing {header_name} header",
            )

        try:
            cookie_token = request.cookies.get(cookie_name)
        except Exception:
            cookie_token = None

        if not cookie_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing CSRF cookie",
            )

        if cookie_token != header_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )
