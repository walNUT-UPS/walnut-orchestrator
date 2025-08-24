"""
System health and diagnostic API endpoints for walNUT platform monitoring.

This module provides REST API endpoints for checking system health status,
configuration information, and testing individual components.
"""

from typing import Dict, Any, Optional, List
import logging
import logging
import io
import json
import zipfile
from pathlib import Path
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from walnut.auth.deps import current_active_user, current_admin
from walnut.auth.models import User
from walnut.core.health import SystemHealthChecker
from walnut.core.app_settings import get_setting, set_setting
from walnut.config import settings as runtime_settings
import threading, os, time, sys, shlex


router = APIRouter()
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Response model for health check endpoints."""
    status: str
    timestamp: str
    components: Dict[str, Any]
    uptime_seconds: int
    last_power_event: str | None = None


class ConfigResponse(BaseModel):
    """Response model for configuration status."""
    version: str
    poll_interval_seconds: int
    heartbeat_timeout_seconds: int
    data_retention_hours: int
    database_type: str
    nut_server: Dict[str, Any]
    cors_enabled: bool
    allowed_origins_count: int


class TestResponse(BaseModel):
    """Response model for component test endpoints."""
    status: str
    details: Dict[str, Any]


class OIDCConfigIn(BaseModel):
    enabled: bool
    provider_name: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    discovery_url: Optional[str] = None
    admin_roles: Optional[List[str]] = None
    viewer_roles: Optional[List[str]] = None


class OIDCConfigOut(BaseModel):
    enabled: bool
    provider_name: Optional[str] = None
    client_id: Optional[str] = None
    has_client_secret: bool = False
    discovery_url: Optional[str] = None
    admin_roles: List[str] = []
    viewer_roles: List[str] = []
    requires_restart: bool = True


# Initialize the health checker
health_checker = SystemHealthChecker()


@router.get(
    "/system/health",
    response_model=HealthResponse,
    responses={500: {"description": "Health check failed due to an internal error."}},
)
async def get_system_health(
    _user: User = Depends(current_active_user)
) -> HealthResponse:
    """
    Get overall system health status.
    
    Returns comprehensive health information including:
    - Overall system status (healthy/degraded/critical)
    - Individual component health status
    - System uptime and last power event
    
    Requires authentication.
    """
    try:
        logger.info("GET /system/health requested")
        health_data = await health_checker.check_overall_health()
        return HealthResponse(**health_data)
    except Exception as e:
        logger.exception("/system/health failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get(
    "/system/config",
    response_model=ConfigResponse,
    responses={500: {"description": "Configuration check failed due to an internal error."}},
)
async def get_system_config(
    _user: User = Depends(current_active_user)
) -> ConfigResponse:
    """
    Get current system configuration status.
    
    Returns non-sensitive configuration settings including:
    - System version and polling intervals
    - Database and NUT server configuration
    - CORS and security settings
    
    Requires authentication.
    """
    try:
        logger.info("GET /system/config requested")
        config_data = await health_checker.get_configuration_status()
        return ConfigResponse(**config_data)
    except Exception as e:
        logger.exception("/system/config failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Configuration check failed: {str(e)}")


@router.get("/system/oidc/config", response_model=OIDCConfigOut)
async def get_oidc_config(_user: User = Depends(current_active_user)) -> OIDCConfigOut:
    """Return stored OIDC configuration merged with runtime defaults."""
    cfg = get_setting("oidc_config") or {}
    enabled = bool(cfg.get("enabled", runtime_settings.OIDC_ENABLED))
    provider_name = cfg.get("provider_name", runtime_settings.OIDC_PROVIDER_NAME)
    client_id = cfg.get("client_id", runtime_settings.OIDC_CLIENT_ID)
    discovery_url = cfg.get("discovery_url", runtime_settings.OIDC_DISCOVERY_URL)
    admin_roles = cfg.get("admin_roles", runtime_settings.OIDC_ADMIN_ROLES or [])
    viewer_roles = cfg.get("viewer_roles", runtime_settings.OIDC_VIEWER_ROLES or [])
    has_secret = bool(cfg.get("client_secret")) or bool(runtime_settings.OIDC_CLIENT_SECRET)
    # Changing this usually requires restart to mount routes
    return OIDCConfigOut(
        enabled=enabled,
        provider_name=provider_name,
        client_id=client_id,
        has_client_secret=has_secret,
        discovery_url=discovery_url,
        admin_roles=admin_roles,
        viewer_roles=viewer_roles,
        requires_restart=True,
    )


@router.put("/system/oidc/config", response_model=OIDCConfigOut)
async def update_oidc_config(payload: OIDCConfigIn, _user: User = Depends(current_active_user)) -> OIDCConfigOut:
    """Persist OIDC configuration to the app settings store."""
    # Store all values; keep existing secret if omitted
    current = get_setting("oidc_config") or {}
    new_cfg: Dict[str, Any] = {
        "enabled": payload.enabled,
        "provider_name": payload.provider_name or current.get("provider_name"),
        "client_id": payload.client_id or current.get("client_id"),
        "client_secret": payload.client_secret or current.get("client_secret"),
        "discovery_url": payload.discovery_url or current.get("discovery_url"),
        "admin_roles": payload.admin_roles or current.get("admin_roles", []),
        "viewer_roles": payload.viewer_roles or current.get("viewer_roles", []),
    }
    set_setting("oidc_config", new_cfg)
    return await get_oidc_config(_user)


@router.post("/system/oidc/test")
async def test_oidc_config(payload: Optional[OIDCConfigIn] = None, _user: User = Depends(current_active_user)) -> Dict[str, Any]:
    """Basic OIDC configuration test: fetch discovery metadata and report endpoints."""
    try:
        cfg = (payload.model_dump() if payload else None) or get_setting("oidc_config") or {}
        discovery_url = cfg.get("discovery_url") or runtime_settings.OIDC_DISCOVERY_URL
        if not discovery_url:
            raise HTTPException(status_code=400, detail="discovery_url is required")

        import httpx
        async with httpx.AsyncClient(timeout=5.0, verify=True) as client:
            r = await client.get(discovery_url)
            r.raise_for_status()
            data = r.json()
        return {
            "status": "success",
            "details": {
                "issuer": data.get("issuer"),
                "authorization_endpoint": data.get("authorization_endpoint"),
                "token_endpoint": data.get("token_endpoint"),
                "userinfo_endpoint": data.get("userinfo_endpoint"),
                "scopes_supported": data.get("scopes_supported"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("OIDC test failed: %s", e)
        raise HTTPException(status_code=500, detail=f"OIDC test failed: {e}")


@router.post("/system/restart")
async def restart_backend(_user: User = Depends(current_admin)) -> Dict[str, Any]:
    """Trigger a backend restart. Process will exit; supervisor or dev reload restarts it.

    Returns immediately while scheduling a delayed exit to allow HTTP response to flush.
    """
    try:
        logger.warning("Backend restart requested by admin")

        def _delayed_exit():
            try:
                time.sleep(0.5)
            except Exception:
                pass
            # Prefer exec of provided restart command, then fall back to re-exec current process
            cmd = os.environ.get("WALNUT_RESTART_CMD")
            if cmd:
                try:
                    os.execl("/bin/sh", "sh", "-c", cmd)
                except Exception:
                    pass
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception:
                os._exit(0)

        threading.Thread(target=_delayed_exit, daemon=True).start()
        return {"status": "restarting"}
    except Exception as e:
        logger.exception("Failed to schedule restart: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to restart: {e}")


@router.post(
    "/system/test/database",
    response_model=TestResponse,
    responses={500: {"description": "Database test failed due to an internal error."}},
)
async def test_database_performance(
    _user: User = Depends(current_active_user)
) -> TestResponse:
    """
    Test database connectivity and performance.
    
    Performs various database operations to test:
    - Basic connectivity
    - Query performance
    - Data retrieval speed
    
    Returns detailed performance metrics.
    Requires authentication.
    """
    try:
        logger.info("POST /system/test/database requested")
        test_results = await health_checker.test_database_performance()
        return TestResponse(
            status=test_results.get("status", "unknown"),
            details=test_results
        )
    except Exception as e:
        logger.exception("/system/test/database failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database test failed: {str(e)}")


@router.post(
    "/system/test/nut",
    response_model=TestResponse,
    responses={500: {"description": "NUT test failed due to an internal error."}},
)
async def test_nut_connection(
    _user: User = Depends(current_active_user)
) -> TestResponse:
    """
    Test NUT server connection and functionality.
    
    Performs comprehensive NUT server tests:
    - Connection establishment
    - UPS device discovery
    - Variable retrieval
    - Response time measurement
    
    Returns detailed connection diagnostics.
    Requires authentication.
    """
    try:
        logger.info("POST /system/test/nut requested")
        test_results = await health_checker.test_nut_connection()
        return TestResponse(
            status=test_results.get("status", "unknown"),
            details=test_results
        )
    except Exception as e:
        logger.exception("/system/test/nut failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NUT test failed: {str(e)}")


@router.get("/system/status")
async def get_basic_status(
    _user: User = Depends(current_active_user)
) -> Dict[str, str]:
    """
    Get basic system status for quick health checks.
    
    Returns minimal status information without detailed diagnostics.
    Useful for load balancer health checks or monitoring systems.
    
    Requires authentication.
    """
    try:
        # Quick health check - just database connectivity
        db_health = await health_checker.check_database_health()
        logger.info("GET /system/status requested -> %s", db_health.status)
        return {
            "status": "ok" if db_health.status == "healthy" else "degraded",
            "timestamp": health_checker._get_current_timestamp(),
            "service": "walNUT"
        }
    except Exception:
        logger.exception("/system/status failed")
        return {
            "status": "error",
            "timestamp": health_checker._get_current_timestamp(),
            "service": "walNUT"
        }


@router.get("/system/diagnostics/bundle")
async def download_diagnostics_bundle(_user: User = Depends(current_active_user)):
    """
    Provide a lightweight diagnostics bundle as a ZIP file.

    Includes:
    - backend log (.tmp/walnut-uvicorn.log) if present
    - frontend log (.tmp/vite.log) if present
    - system health JSON
    - system config JSON
    """
    # Collect health and config
    health_data = await health_checker.check_overall_health()
    config_data = await health_checker.get_configuration_status()

    # Prepare in-memory ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("diagnostics/health.json", json.dumps(health_data, indent=2))
        zf.writestr("diagnostics/config.json", json.dumps(config_data, indent=2))

        # Add logs if available
        backend_log = Path(".tmp/walnut-uvicorn.log")
        frontend_log = Path(".tmp/vite.log")
        if backend_log.exists():
            try:
                zf.write(backend_log, arcname="logs/backend-uvicorn.log")
            except Exception:
                pass
        if frontend_log.exists():
            try:
                zf.write(frontend_log, arcname="logs/frontend-vite.log")
            except Exception:
                pass

    buf.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=walnut-diagnostics-{health_checker._get_current_timestamp().replace(':','-')}.zip"
    }
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


# Add a helper method to the health checker for consistent timestamps
def _get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

# Monkey patch the method (not ideal but keeps it simple)
SystemHealthChecker._get_current_timestamp = _get_current_timestamp
# Simple CSRF token provider for frontend
@router.get("/csrf-token")
async def get_csrf_token() -> Dict[str, str]:
    """
    Return a CSRF token value for clients to echo in X-CSRF-Token.
    Current CSRF protection only checks for header presence, not value.
    """
    return {"csrf_token": uuid4().hex}
