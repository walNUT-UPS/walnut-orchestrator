"""
Workers API stubs.

These endpoints intentionally return 204 No Content to suppress 404 noise
in development environments where background workers are not running.
"""
from fastapi import APIRouter, Response, status, Depends
from walnut.auth.csrf import csrf_protect

router = APIRouter(dependencies=[Depends(csrf_protect)])


@router.post("/workers/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def workers_heartbeat() -> Response:
    """No-op heartbeat endpoint for workers. Returns 204 to avoid 404 spam."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workers/{_rest:path}", status_code=status.HTTP_204_NO_CONTENT)
@router.post("/workers/{_rest:path}", status_code=status.HTTP_204_NO_CONTENT)
@router.put("/workers/{_rest:path}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/workers/{_rest:path}", status_code=status.HTTP_204_NO_CONTENT)
async def workers_catch_all(_rest: str) -> Response:
    """Catch-all for other /workers/* routes to quietly no-op with 204."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
