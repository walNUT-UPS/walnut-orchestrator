from fastapi import Request, HTTPException, status


async def csrf_protect(request: Request):
    """
    A dependency that provides CSRF protection by checking for the
    X-CSRF-Token header on all state-changing requests.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if "x-csrf-token" not in request.headers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing X-CSRF-Token header",
            )
