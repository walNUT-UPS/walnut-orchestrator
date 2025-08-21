"""
System health and diagnostic API endpoints for walNUT platform monitoring.

This module provides REST API endpoints for checking system health status,
configuration information, and testing individual components.
"""

from typing import Dict, Any
import logging
import io
import json
import zipfile
from pathlib import Path
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.core.health import SystemHealthChecker


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
