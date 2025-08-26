"""
Health checking utilities for walNUT system monitoring.

This module provides comprehensive health checks for various system components
including database connectivity, NUT server connection, UPS polling status,
authentication system health, and system resources.
"""

import asyncio
import logging
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import psutil
import anyio
from sqlalchemy import text

from walnut.config import settings
from walnut.database.connection import get_db_session
from walnut.database.models import UPSSample, EventBus
from walnut.nut.client import NUTClient, NUTConnectionError

logger = logging.getLogger(__name__)


class HealthStatus:
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class ComponentHealth:
    """Health information for a system component."""
    
    def __init__(self, status: str, **kwargs):
        self.status = status
        self.details = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, **self.details}


class SystemHealthChecker:
    """Comprehensive system health checker."""
    
    def __init__(self):
        self.start_time = time.time()
    
    async def check_overall_health(self) -> Dict[str, Any]:
        """
        Check overall system health and return comprehensive status.
        
        Returns:
            Dictionary containing overall health status and component details
        """
        components = {
            "database": await self.check_database_health(),
            "nut_connection": await self.check_nut_connection(),
            "ups_polling": await self.check_ups_polling(),
            "disk_space": self.check_disk_space(),
            "system_resources": self.check_system_resources(),
        }
        
        # Determine overall status
        overall_status = self._determine_overall_status(components)
        
        # Get last power event
        last_power_event = await self._get_last_power_event()
        
        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {name: comp.to_dict() for name, comp in components.items()},
            "uptime_seconds": int(time.time() - self.start_time),
            "last_power_event": last_power_event,
        }
    
    async def check_database_health(self) -> ComponentHealth:
        """
        Check database connectivity and performance.
        
        Returns:
            ComponentHealth object with database status
        """
        try:
            start_time = time.time()
            async with get_db_session() as session:
                # Simple connectivity test
                result = await anyio.to_thread.run_sync(session.execute, text("SELECT 1"))
                await anyio.to_thread.run_sync(result.fetchone)
                
                # Performance test - count recent samples
                count_result = await anyio.to_thread.run_sync(
                    session.execute,
                    text("SELECT COUNT(*) FROM ups_samples WHERE timestamp > datetime('now', '-1 hour')")
                )
                recent_samples = await anyio.to_thread.run_sync(count_result.scalar) or 0
                
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            if latency_ms > 1000:  # > 1 second
                return ComponentHealth(
                    HealthStatus.DEGRADED,
                    latency_ms=latency_ms,
                    recent_samples=recent_samples,
                    message="High database latency"
                )
            
            return ComponentHealth(
                HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                recent_samples=recent_samples
            )
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                HealthStatus.CRITICAL,
                error=str(e),
                message="Database connection failed"
            )
    
    async def check_nut_connection(self) -> ComponentHealth:
        """
        Check NUT server connection status by querying the actual running NUT service.
        
        Returns:
            ComponentHealth object with NUT connection status
        """
        try:
            # Import here to avoid circular imports
            from ..app import nut_service
            
            # Check if NUT service is running
            if not nut_service:
                return ComponentHealth(
                    HealthStatus.CRITICAL,
                    message="NUT service not initialized"
                )
            
            # Get poller status from the running service
            poller_status = nut_service.get_poller_status()
            
            if not poller_status:
                return ComponentHealth(
                    HealthStatus.DEGRADED,
                    message="No UPS devices being monitored"
                )
            
            # Check each poller
            healthy_count = 0
            total_count = len(poller_status)
            disconnected_devices = []
            
            for ups_name, status in poller_status.items():
                if status["is_running"] and not status["is_disconnected"]:
                    healthy_count += 1
                else:
                    disconnected_devices.append(ups_name)
            
            if healthy_count == total_count:
                return ComponentHealth(
                    HealthStatus.HEALTHY,
                    ups_count=total_count,
                    ups_devices=list(poller_status.keys()),
                    message=f"All {total_count} UPS device(s) connected and polling"
                )
            elif healthy_count > 0:
                return ComponentHealth(
                    HealthStatus.DEGRADED,
                    ups_count=total_count,
                    healthy_count=healthy_count,
                    disconnected_devices=disconnected_devices,
                    message=f"{healthy_count}/{total_count} UPS devices healthy"
                )
            else:
                return ComponentHealth(
                    HealthStatus.CRITICAL,
                    ups_count=total_count,
                    disconnected_devices=disconnected_devices,
                    message="All UPS devices disconnected or not polling"
                )
            
        except Exception as e:
            logger.error(f"NUT service health check failed: {e}")
            return ComponentHealth(
                HealthStatus.CRITICAL,
                error=str(e),
                message="Failed to check NUT service status"
            )
    
    async def check_ups_polling(self) -> ComponentHealth:
        """
        Check recent UPS polling success rate.
        
        Returns:
            ComponentHealth object with UPS polling status
        """
        try:
            async with get_db_session() as session:
                # Count samples in last hour
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                
                result = await anyio.to_thread.run_sync(
                    session.execute,
                    text("SELECT COUNT(*) FROM ups_samples WHERE timestamp > :cutoff"),
                    {"cutoff": one_hour_ago}
                )
                samples_last_hour = await anyio.to_thread.run_sync(result.scalar) or 0
                
                # Get latest sample timestamp
                latest_result = await anyio.to_thread.run_sync(
                    session.execute,
                    text("SELECT MAX(timestamp) FROM ups_samples")
                )
                latest_timestamp = await anyio.to_thread.run_sync(latest_result.scalar)
                
                # Expected samples per hour (assuming 5 second polling interval)
                expected_samples = 720  # 60 * 60 / 5
                success_rate = min(100, (samples_last_hour / expected_samples) * 100)
                
                # Check if polling is recent (within last 4 poll intervals for more tolerance)
                if latest_timestamp:
                    latest_dt = datetime.fromisoformat(latest_timestamp.replace('Z', '+00:00'))
                    # Ensure both datetimes are timezone-aware
                    if latest_dt.tzinfo is None:
                        latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                    time_since_last = (datetime.now(timezone.utc) - latest_dt).total_seconds()
                    max_gap = settings.POLL_INTERVAL * 4  # More tolerance for real-world conditions
                    
                    if time_since_last > max_gap:
                        return ComponentHealth(
                            HealthStatus.CRITICAL,
                            samples_last_hour=samples_last_hour,
                            success_rate=round(success_rate, 1),
                            last_poll=latest_timestamp,
                            seconds_since_last=int(time_since_last),
                            message="UPS polling appears to have stopped"
                        )
                
                # More realistic thresholds for production environments
                # If we have recent data and reasonable sample count, consider it healthy
                if samples_last_hour >= 180:  # At least one sample every 20 seconds on average
                    status = HealthStatus.HEALTHY
                    message = None
                elif samples_last_hour >= 60:  # At least one sample per minute on average
                    status = HealthStatus.DEGRADED
                    message = "Reduced UPS polling frequency"
                else:
                    status = HealthStatus.CRITICAL
                    message = "Very low UPS polling success rate"
                
                return ComponentHealth(
                    status,
                    samples_last_hour=samples_last_hour,
                    success_rate=round(success_rate, 1),
                    last_poll=latest_timestamp,
                    **({"message": message} if message else {})
                )
                
        except Exception as e:
            logger.error(f"UPS polling health check failed: {e}")
            return ComponentHealth(
                HealthStatus.CRITICAL,
                error=str(e),
                message="UPS polling health check failed"
            )
    
    def check_disk_space(self) -> ComponentHealth:
        """
        Check available disk space.
        
        Returns:
            ComponentHealth object with disk space status
        """
        try:
            # Get disk usage for current directory
            total, used, free = shutil.disk_usage('.')
            free_gb = free / (1024 ** 3)
            free_percent = (free / total) * 100
            
            if free_gb < 1.0 or free_percent < 5:
                status = HealthStatus.CRITICAL
                message = "Very low disk space"
            elif free_gb < 5.0 or free_percent < 10:
                status = HealthStatus.DEGRADED
                message = "Low disk space"
            else:
                status = HealthStatus.HEALTHY
                message = None
            
            return ComponentHealth(
                status,
                free_gb=round(free_gb, 1),
                free_percent=round(free_percent, 1),
                total_gb=round(total / (1024 ** 3), 1),
                **({"message": message} if message else {})
            )
            
        except Exception as e:
            logger.error(f"Disk space health check failed: {e}")
            return ComponentHealth(
                HealthStatus.CRITICAL,
                error=str(e),
                message="Disk space check failed"
            )
    
    def check_system_resources(self) -> ComponentHealth:
        """
        Check system resource usage (CPU, memory).
        
        Returns:
            ComponentHealth object with system resource status
        """
        try:
            # Get CPU usage (1 second average)
            cpu_percent = psutil.cpu_percent(interval=1.0)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Get load average (if available)
            load_avg = None
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()[0]  # 1-minute load average
            
            # Determine status - more realistic thresholds for working systems
            if cpu_percent > 95 or memory_percent > 98:
                status = HealthStatus.CRITICAL
                message = "Very high system resource usage"
            elif cpu_percent > 85 or memory_percent > 92:
                status = HealthStatus.DEGRADED
                message = "High system resource usage"
            else:
                status = HealthStatus.HEALTHY
                message = None
            
            result_data = {
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory_percent, 1),
                "memory_available_gb": round(memory.available / (1024 ** 3), 1),
            }
            
            if load_avg is not None:
                result_data["load_average_1min"] = round(load_avg, 2)
            
            if message:
                result_data["message"] = message
            
            return ComponentHealth(status, **result_data)
            
        except Exception as e:
            logger.error(f"System resource health check failed: {e}")
            return ComponentHealth(
                HealthStatus.CRITICAL,
                error=str(e),
                message="System resource check failed"
            )
    
    async def test_database_performance(self) -> Dict[str, Any]:
        """
        Test database performance with various operations.
        
        Returns:
            Dictionary with performance test results
        """
        results = {}
        
        try:
            async with get_db_session() as session:
                # Test 1: Simple query
                start_time = time.time()
                await anyio.to_thread.run_sync(session.execute, text("SELECT 1"))
                results["simple_query_ms"] = round((time.time() - start_time) * 1000, 2)
                
                # Test 2: Count records
                start_time = time.time()
                result = await anyio.to_thread.run_sync(session.execute, text("SELECT COUNT(*) FROM ups_samples"))
                total_samples = await anyio.to_thread.run_sync(result.scalar) or 0
                results["count_query_ms"] = round((time.time() - start_time) * 1000, 2)
                results["total_samples"] = total_samples
                
                # Test 3: Recent data query
                start_time = time.time()
                await anyio.to_thread.run_sync(
                    session.execute,
                    text("SELECT * FROM ups_samples WHERE timestamp > datetime('now', '-1 hour') LIMIT 100")
                )
                results["recent_data_query_ms"] = round((time.time() - start_time) * 1000, 2)
                
                results["status"] = "success"
                
        except Exception as e:
            logger.error(f"Database performance test failed: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
        
        return results
    
    async def test_nut_connection(self) -> Dict[str, Any]:
        """
        Test NUT server connection with detailed diagnostics.
        
        Returns:
            Dictionary with NUT connection test results
        """
        results = {}
        
        try:
            client = NUTClient()
            
            # Test 1: List UPS devices
            start_time = time.time()
            ups_list = await asyncio.wait_for(client.list_ups(), timeout=10.0)
            results["list_ups_ms"] = round((time.time() - start_time) * 1000, 2)
            results["ups_devices"] = list(ups_list.keys()) if ups_list else []
            
            # Test 2: Get variables for first UPS (if available)
            if ups_list:
                first_ups = list(ups_list.keys())[0]
                start_time = time.time()
                ups_vars = await asyncio.wait_for(client.get_vars(first_ups), timeout=10.0)
                results["get_vars_ms"] = round((time.time() - start_time) * 1000, 2)
                results["vars_count"] = len(ups_vars)
                results["test_ups"] = first_ups
                
                # Include some key variables
                key_vars = ["battery.charge", "ups.status", "ups.load", "battery.runtime"]
                results["key_variables"] = {
                    var: ups_vars.get(var) for var in key_vars if var in ups_vars
                }
            
            results["status"] = "success"
            
        except NUTConnectionError as e:
            results["status"] = "failed"
            results["error"] = "NUT connection error"
            results["details"] = str(e)
        except asyncio.TimeoutError:
            results["status"] = "failed"
            results["error"] = "Connection timeout"
        except Exception as e:
            logger.error(f"NUT connection test failed: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
        
        return results
    
    async def get_configuration_status(self) -> Dict[str, Any]:
        """
        Get current non-sensitive configuration status.
        
        Returns:
            Dictionary with current configuration settings
        """
        # Use package version for accuracy
        try:
            from walnut import __version__ as version
        except Exception:
            version = "0.0.0"
        return {
            "version": version,
            "poll_interval_seconds": settings.POLL_INTERVAL,
            "heartbeat_timeout_seconds": settings.HEARTBEAT_TIMEOUT,
            "data_retention_hours": settings.DATA_RETENTION_HOURS,
            "database_type": "SQLCipher",
            "nut_server": {
                "host": settings.NUT_HOST,
                "port": settings.NUT_PORT,
                "username": settings.NUT_USERNAME or "anonymous",
                "password_configured": bool(settings.NUT_PASSWORD),
            },
            "cors_enabled": bool(settings.ALLOWED_ORIGINS),
            "allowed_origins_count": len(settings.ALLOWED_ORIGINS) if settings.ALLOWED_ORIGINS else 0,
            "secure_cookies": bool(settings.SECURE_COOKIES),
            "signup_enabled": bool(settings.SIGNUP_ENABLED),
        }
    
    def _determine_overall_status(self, components: Dict[str, ComponentHealth]) -> str:
        """
        Determine overall system status based on component health.
        
        Args:
            components: Dictionary of component health checks
            
        Returns:
            Overall system status string
        """
        critical_count = sum(1 for comp in components.values() if comp.status == HealthStatus.CRITICAL)
        degraded_count = sum(1 for comp in components.values() if comp.status == HealthStatus.DEGRADED)
        
        if critical_count > 0:
            return HealthStatus.CRITICAL
        elif degraded_count > 0:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
    
    async def _get_last_power_event(self) -> Optional[str]:
        """
        Get timestamp of the last power-related event.
        
        Returns:
            ISO timestamp string of last power event or None
        """
        try:
            async with get_db_session() as session:
                # Look for power-related events in the new event_bus table
                result = await anyio.to_thread.run_sync(
                    session.execute,
                    text("""
                        SELECT MAX(occurred_at) FROM event_bus 
                        WHERE type IN ('MAINS_LOST', 'MAINS_RETURNED', 'LOW_BATTERY', 'BATTERY_WARNING')
                    """)
                )
                timestamp = await anyio.to_thread.run_sync(result.scalar)
                return timestamp.isoformat() if timestamp else None
                
        except Exception as e:
            logger.error(f"Failed to get last power event: {e}")
            return None
