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
import time
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


class NUTConfigIn(BaseModel):
    """Input model for NUT server configuration."""
    host: str
    port: int = 3493
    username: Optional[str] = None
    password: Optional[str] = None


class NUTConfigOut(BaseModel):
    """Output model for NUT server configuration."""
    host: str
    port: int
    username: Optional[str] = None
    password_configured: bool = False


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


@router.get("/system/nut/config", response_model=NUTConfigOut)
async def get_nut_config(_user: User = Depends(current_active_user)) -> NUTConfigOut:
    """Return stored NUT configuration merged with runtime defaults."""
    current = get_setting("nut_config") or {}
    return NUTConfigOut(
        host=current.get("host") or runtime_settings.NUT_HOST,
        port=current.get("port") or runtime_settings.NUT_PORT,
        username=current.get("username") or runtime_settings.NUT_USERNAME,
        password_configured=bool(current.get("password") or runtime_settings.NUT_PASSWORD),
    )


@router.put("/system/nut/config", response_model=NUTConfigOut)
async def update_nut_config(payload: NUTConfigIn, _user: User = Depends(current_active_user)) -> NUTConfigOut:
    """Persist NUT configuration to the app settings store."""
    # Store all values; keep existing password if omitted  
    current = get_setting("nut_config") or {}
    new_cfg: Dict[str, Any] = {
        "host": payload.host,
        "port": payload.port,
        "username": payload.username or current.get("username"),
        "password": payload.password or current.get("password"),
    }
    set_setting("nut_config", new_cfg)
    
    # Restart NUT service with new configuration
    try:
        from walnut.app import nut_service
        if nut_service:
            import asyncio
            asyncio.create_task(nut_service.restart_with_new_config())
            logger.info("Scheduled NUT service restart with new configuration")
    except Exception as e:
        logger.exception(f"Failed to restart NUT service with new config: {e}")
    
    return await get_nut_config(_user)


@router.post("/system/nut/test")
async def test_nut_config(payload: Optional[NUTConfigIn] = None, _user: User = Depends(current_active_user)) -> Dict[str, Any]:
    """Test NUT server connection with specified or stored configuration."""
    try:
        cfg = (payload.model_dump() if payload else None) or get_setting("nut_config") or {}
        host = cfg.get("host") or runtime_settings.NUT_HOST
        port = cfg.get("port") or runtime_settings.NUT_PORT  
        username = cfg.get("username") or runtime_settings.NUT_USERNAME
        password = cfg.get("password") or runtime_settings.NUT_PASSWORD
        
        from walnut.nut.client import NUTClient
        import asyncio
        
        client = NUTClient(host=host, port=port, username=username, password=password)
        
        # Test connection
        start_time = time.time()
        ups_list = await asyncio.wait_for(client.list_ups(), timeout=10.0)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        if not ups_list:
            return {
                "status": "warning",
                "details": {
                    "message": "Connected to NUT server but no UPS devices found",
                    "host": host,
                    "port": port,
                    "latency_ms": latency_ms,
                    "ups_devices": []
                }
            }
        
        # Test getting variables from first UPS
        ups_details = {}
        first_ups = list(ups_list.keys())[0]
        try:
            ups_vars = await asyncio.wait_for(client.get_vars(first_ups), timeout=10.0)
            ups_details = {
                var: ups_vars.get(var) 
                for var in ["battery.charge", "ups.status", "ups.load", "battery.runtime", "ups.model"]
                if var in ups_vars
            }
        except Exception as e:
            logger.warning(f"Could not get variables from UPS {first_ups}: {e}")
        
        return {
            "status": "success",
            "details": {
                "message": f"Successfully connected to NUT server with {len(ups_list)} UPS device(s)",
                "host": host,
                "port": port,
                "latency_ms": latency_ms,
                "ups_devices": list(ups_list.keys()),
                "ups_descriptions": ups_list,
                "sample_ups_data": ups_details
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("NUT test failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NUT connection test failed: {str(e)}")


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


@router.get("/system/nut/status")
async def get_nut_service_status(
    _user: User = Depends(current_active_user)
) -> Dict[str, Any]:
    """
    Get NUT service status and monitored UPS devices.
    
    Returns information about the NUT polling service including:
    - Active UPS devices being monitored
    - Poller status for each device
    - Service health information
    
    Requires authentication.
    """
    try:
        from walnut.app import nut_service
        
        if not nut_service:
            return {
                "status": "not_started",
                "message": "NUT service has not been initialized",
                "active_devices": [],
                "pollers": {}
            }
        
        active_devices = nut_service.get_active_ups_devices()
        poller_status = nut_service.get_poller_status()
        
        return {
            "status": "running" if active_devices else "no_devices",
            "message": f"Monitoring {len(active_devices)} UPS device(s)" if active_devices else "No UPS devices found",
            "active_devices": active_devices,
            "pollers": poller_status,
            "nut_server": {
                "host": runtime_settings.NUT_HOST,
                "port": runtime_settings.NUT_PORT,
                "username": runtime_settings.NUT_USERNAME or "anonymous"
            }
        }
    except Exception as e:
        logger.exception("GET /system/nut/status failed: %s", e)
        return {
            "status": "error",
            "message": f"Failed to get NUT service status: {str(e)}",
            "active_devices": [],
            "pollers": {}
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
