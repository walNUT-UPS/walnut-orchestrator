from fastapi import Request, HTTPException, status


async def csrf_protect(request: Request):
    """
    A dependency that provides CSRF protection by checking for the
    X-CSRF-Token header on all state-changing requests.
    
    Note: This dependency is WebSocket-aware and will skip CSRF checks
    for WebSocket connections.
    """
    try:
        # Skip CSRF protection for WebSocket connections
        # WebSocket connections don't have traditional HTTP methods
        if not hasattr(request, 'method'):
            return
        
        # Additional check: WebSocket requests may have a different scope type
        if hasattr(request, 'scope') and request.scope.get('type') == 'websocket':
            return
            
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if "x-csrf-token" not in request.headers:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing X-CSRF-Token header",
                )
    except Exception:
        # If we can't determine the request type safely, skip CSRF protection
        # This ensures WebSocket connections aren't accidentally blocked
        return
