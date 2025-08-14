"""
Main FastAPI application file for walNUT.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from walnut.auth.router import auth_router, api_router
from walnut.config import settings
from walnut.api import policies, policy_runs, admin_events, ups, events, system
from walnut.api.websocket import websocket_endpoint, get_websocket_info


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

# WebSocket endpoints
@app.websocket("/ws")
async def websocket_main_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket_endpoint(websocket, token)

@app.websocket("/ws/updates")
async def websocket_updates_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket_endpoint(websocket, token)

# Add WebSocket info endpoint for debugging
@app.get("/api/websocket/info")
async def websocket_info():
    return await get_websocket_info()


@app.get("/")
async def root():
    return {"message": "Welcome to walNUT!"}

