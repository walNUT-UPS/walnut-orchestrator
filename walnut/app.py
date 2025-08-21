"""
Main FastAPI application file for walNUT.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from walnut.auth.router import auth_router, api_router
from walnut.config import settings
from walnut.api import policies, policy_runs, admin_events, ups, events, system, integrations
from walnut.api.websocket import websocket_endpoint, get_websocket_info
from fastapi import WebSocket, Query
from typing import Optional
from walnut.api.websocket import authenticate_websocket_token
from walnut.core.websocket_manager import websocket_manager


app = FastAPI(
    title="walNUT API",
    description="walNUT - UPS Management Platform with Network UPS Tools (NUT) integration",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth_router, prefix="/auth")
app.include_router(api_router, prefix="/api")
app.include_router(policies.router, prefix="/api", tags=["Policies"])
app.include_router(policy_runs.router, prefix="/api", tags=["Policy Runs"])
app.include_router(admin_events.router, prefix="/api/admin", tags=["Admin"])
app.include_router(ups.router, prefix="/api", tags=["UPS Monitoring"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(system.router, prefix="/api", tags=["System Health"])
app.include_router(integrations.router, prefix="/api", tags=["Integrations"])

# WebSocket endpoints
@app.websocket("/ws")
async def websocket_main_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket_endpoint(websocket, token)

@app.websocket("/ws/updates")
async def websocket_updates_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket_endpoint(websocket, token)


@app.websocket("/ws/integrations/jobs/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str, token: Optional[str] = Query(None)):
    client_id = None
    try:
        # Cookie fallback for token
        cookie_token = None
        try:
            cookies = websocket.cookies or {}
            for name in ("walnut_access", "fastapiusersauth", "fastapi_users_auth", "auth", "session"):
                if name in cookies:
                    cookie_token = cookies.get(name)
                    if cookie_token:
                        break
        except Exception:
            cookie_token = None

        if not token:
            token = cookie_token

        if not token:
            await websocket.close(code=4001, reason="Authentication token required")
            return

        user = await authenticate_websocket_token(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

        client_id = await websocket_manager.connect(websocket)
        websocket_manager.authenticate_client(client_id, str(user.id))
        websocket_manager.subscribe_job(job_id, client_id)

        await websocket.send_json({"type": "job_stream.open", "data": {"job_id": job_id, "client_id": client_id}})

        while True:
            await websocket.receive_text()

    except Exception:
        pass
    finally:
        if client_id:
            websocket_manager.unsubscribe_job(job_id, client_id)
            await websocket_manager.disconnect(client_id)

# Public health check for testing
@app.get("/health")
async def public_health_check():
    """Public health check endpoint for testing"""
    return {
        "status": "ok",
        "service": "walNUT",
        "message": "Backend is running",
        "auth_required": False
    }

# Public API health check for testing proxy
@app.get("/api/health")
async def api_health_check():
    """Public API health check endpoint for testing proxy"""
    return {
        "status": "ok",
        "service": "walNUT API",
        "message": "API proxy is working",
        "auth_required": False
    }

# Add WebSocket info endpoint for debugging
@app.get("/api/websocket/info")
async def websocket_info():
    return await get_websocket_info()


@app.get("/")
async def root():
    return {"message": "Welcome to walNUT!"}
