"""
Main FastAPI application file for walNUT.
"""
from contextlib import asynccontextmanager
import logging
import time
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware

from walnut.auth.router import auth_router, api_router
from walnut.config import settings
from walnut.api import policies, policy_runs, admin_events, ups, events, system, integrations, hosts
from walnut.api.websocket import websocket_endpoint, get_websocket_info
from walnut.api.websocket import authenticate_websocket_token
from walnut.core.websocket_manager import websocket_manager
import asyncio
from pathlib import Path

from walnut.transports.registry import init_transports
from walnut.core.integration_registry import get_integration_registry
from walnut.database.connection import get_db_session
from walnut.database.models import IntegrationType
import anyio
from walnut.utils.logging import setup_logging

logger = logging.getLogger("walnut.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    # On startup
    setup_logging()
    logger.info("Initializing walNUT services...")
    init_transports()
    logger.info("Transport adapters initialized.")
    logger.info(
        "App settings: cors=%s origins=%s secure_cookies=%s poll_interval=%s",
        bool(settings.ALLOWED_ORIGINS),
        settings.ALLOWED_ORIGINS,
        settings.SECURE_COOKIES,
        settings.POLL_INTERVAL,
    )
    # Auto-scan integrations on first boot (when no types exist in DB)
    try:
        async with get_db_session() as session:
            def _count_types():
                return session.query(IntegrationType).count()

            types_count = await anyio.to_thread.run_sync(_count_types)

        if types_count == 0:
            logger.info("First boot detected: no integration types found. Starting discovery & validation...")
            registry = get_integration_registry()
            # Run asynchronously so API becomes available immediately
            asyncio.create_task(registry.discover_and_validate_all(force_rescan=True))
        else:
            logger.info("Integration types present in DB: %d — skipping first-boot scan", types_count)
    except Exception:
        logger.exception("Failed to run first-boot integration scan check")
    # TODO: Add other startup logic here (e.g., DB connection pool, discovery)
    yield
    # On shutdown
    logger.info("Shutting down walNUT services...")


app = FastAPI(
    title="walNUT API",
    description="walNUT - UPS Management Platform with Network UPS Tools (NUT) integration",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware (complements Uvicorn access logs)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    path = request.url.path
    method = request.method
    try:
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("%s %s -> %s in %dms", method, path, response.status_code, duration_ms)
        return response
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception("%s %s -> 500 in %dms (error: %s)", method, path, duration_ms, e)
        raise

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
app.include_router(hosts.router, prefix="/api", tags=["Hosts"])

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
        logger.info("WS /ws/integrations/jobs/%s connect attempt", job_id)
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
        logger.exception("WS job stream error for job_id=%s client_id=%s", job_id, client_id)
    finally:
        if client_id:
            websocket_manager.unsubscribe_job(job_id, client_id)
            await websocket_manager.disconnect(client_id)
            logger.info("WS job stream closed for job_id=%s client_id=%s", job_id, client_id)


# Simple log streaming over WebSocket for diagnostics
@app.websocket("/ws/logs/{source}")
async def websocket_logs_endpoint(websocket: WebSocket, source: str, token: Optional[str] = Query(None)):
    """
    Streams log lines from backend or frontend dev servers to the client.

    Sources:
    - backend: ./.tmp/walnut-uvicorn.log
    - frontend: ./.tmp/vite.log
    """
    # Authenticate via token or cookie as with other endpoints
    try:
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

        await websocket.accept()
        logger.info("WS /ws/logs/%s opened", source)

        # Determine log file path
        if source == "backend":
            log_path = Path(".tmp/walnut-uvicorn.log")
        elif source == "frontend":
            log_path = Path(".tmp/vite.log")
        else:
            await websocket.send_json({"type": "log.error", "data": {"message": f"Unknown source: {source}"}})
            await websocket.close()
            return

        # Send an info banner
        await websocket.send_json({"type": "log.open", "data": {"source": source, "path": str(log_path)}})

        # If file doesn't exist yet, wait a bit and inform client
        retries = 0
        while not log_path.exists() and retries < 20:
            await websocket.send_json({"type": "log.info", "data": {"message": f"Waiting for {source} logs..."}})
            await asyncio.sleep(0.5)
            retries += 1

        if not log_path.exists():
            await websocket.send_json({"type": "log.error", "data": {"message": f"Log file not found: {log_path}"}})
            logger.warning("WS logs source %s missing file %s", source, log_path)
            await websocket.close()
            return

        # Tail the file: send last 200 lines, then stream new ones
        try:
            with log_path.open("r", encoding="utf-8", errors="ignore") as f:
                # Read last N lines efficiently
                try:
                    f.seek(0, 2)
                    file_size = f.tell()
                    block = 2048
                    data = ""
                    while file_size > 0 and data.count("\n") < 200:
                        step = block if file_size >= block else file_size
                        file_size -= step
                        f.seek(file_size)
                        data = f.read(step) + data
                    last_lines = data.splitlines()[-200:]
                except Exception:
                    f.seek(0)
                    last_lines = f.read().splitlines()[-200:]

                for line in last_lines:
                    await websocket.send_json({"type": "log.line", "data": {"source": source, "line": line}})

                # Now stream new lines
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    await websocket.send_json({"type": "log.line", "data": {"source": source, "line": line.rstrip('\n')}})
        except Exception:
            # Swallow errors; client likely disconnected
            logger.exception("WS logs stream error for source=%s", source)
            pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
        finally:
            logger.info("WS /ws/logs/%s closed", source)

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
