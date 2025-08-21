"""
Main FastAPI application file for walNUT.
"""
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from walnut.config import Settings, settings as default_settings

def create_app(settings_override: Optional[Settings] = None) -> FastAPI:
    app_settings = settings_override or default_settings

    app = FastAPI(
        title="walNUT API",
        description="walNUT - UPS Management Platform with Network UPS Tools (NUT) integration",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.ALLOWED_ORIGINS if app_settings.ALLOWED_ORIGINS else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # These imports must be inside create_app to use the correct settings
    from walnut.auth.router import auth_router, api_router
    from walnut.api import policies, policy_runs, admin_events, ups, events, system, integrations
    from walnut.api.websocket import websocket_endpoint, get_websocket_info

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

    # Public health check for testing
    @app.get("/health")
    async def public_health_check():
        return {"status": "ok"}

    # Public API health check for testing proxy
    @app.get("/api/health")
    async def api_health_check():
        return {"status": "ok"}

    # Add WebSocket info endpoint for debugging
    @app.get("/api/websocket/info")
    async def websocket_info():
        return await get_websocket_info()

    @app.get("/")
    async def root():
        return {"message": "Welcome to walNUT!"}

    return app

app = create_app()
