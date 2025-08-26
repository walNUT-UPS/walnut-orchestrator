"""
NUT Polling Service for walNUT.

This module provides a service that automatically discovers UPS devices
and starts polling them for real-time data.
"""

import asyncio
import logging
from typing import Dict, List

from ..nut.client import NUTClient, NUTConnectionError
from ..nut.poller import NUTPoller
from ..config import settings
from .app_settings import get_setting

logger = logging.getLogger(__name__)


class NUTService:
    """
    Service that manages NUT polling for all discovered UPS devices.
    """
    
    def __init__(self):
        self.pollers: Dict[str, NUTPoller] = {}
        self._discovery_task: asyncio.Task | None = None
        self._should_stop = asyncio.Event()
        self._client = None  # Will be created with current config
        
    def _get_nut_config(self):
        """Get current NUT configuration from settings or fallback to environment."""
        saved_config = get_setting("nut_config") or {}
        return {
            "host": saved_config.get("host") or settings.NUT_HOST,
            "port": saved_config.get("port") or settings.NUT_PORT,
            "username": saved_config.get("username") or settings.NUT_USERNAME,
            "password": saved_config.get("password") or settings.NUT_PASSWORD,
        }
    
    def _get_client(self):
        """Get NUT client with current configuration."""
        config = self._get_nut_config()
        return NUTClient(
            host=config["host"],
            port=config["port"], 
            username=config["username"],
            password=config["password"]
        )
        
    async def start(self):
        """Start the NUT service."""
        logger.info("Starting NUT service...")
        self._should_stop.clear()
        
        # Start initial discovery
        await self._discover_and_start_pollers()
        
        # Start periodic discovery task
        self._discovery_task = asyncio.create_task(self._periodic_discovery())
        logger.info("NUT service started successfully")
        
    async def stop(self):
        """Stop the NUT service and all pollers."""
        logger.info("Stopping NUT service...")
        self._should_stop.set()
        
        # Stop discovery task
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        
        # Stop all pollers
        stop_tasks = [poller.stop() for poller in self.pollers.values()]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self.pollers.clear()
        logger.info("NUT service stopped")
    
    async def _discover_and_start_pollers(self):
        """Discover UPS devices and start pollers for them."""
        try:
            config = self._get_nut_config()
            logger.info(f"Discovering UPS devices on {config['host']}:{config['port']}")
            client = self._get_client()
            ups_list = await asyncio.wait_for(client.list_ups(), timeout=10.0)
            
            if not ups_list:
                logger.warning("No UPS devices found on NUT server")
                return
            
            logger.info(f"Found {len(ups_list)} UPS device(s): {list(ups_list.keys())}")
            
            # Start poller for each discovered UPS
            for ups_name, ups_description in ups_list.items():
                if ups_name not in self.pollers:
                    logger.info(f"Starting poller for UPS '{ups_name}' ({ups_description})")
                    poller = NUTPoller(
                        ups_name=ups_name,
                        host=config["host"],
                        port=config["port"],
                        username=config["username"],
                        password=config["password"]
                    )
                    await poller.start()
                    self.pollers[ups_name] = poller
                    
        except NUTConnectionError as e:
            logger.error(f"Failed to connect to NUT server: {e}")
        except asyncio.TimeoutError:
            logger.error("Timeout connecting to NUT server")
        except Exception as e:
            logger.exception(f"Unexpected error during UPS discovery: {e}")
    
    async def _periodic_discovery(self):
        """Periodically check for new UPS devices."""
        # Run discovery every 5 minutes
        discovery_interval = 300
        
        while not self._should_stop.is_set():
            try:
                await asyncio.sleep(discovery_interval)
                if not self._should_stop.is_set():
                    await self._discover_and_start_pollers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in periodic UPS discovery: {e}")
    
    async def restart_with_new_config(self):
        """Restart the service with updated configuration."""
        logger.info("Restarting NUT service with updated configuration...")
        await self.stop()
        await self.start()
        logger.info("NUT service restarted successfully")
    
    def get_active_ups_devices(self) -> List[str]:
        """Get list of currently monitored UPS devices."""
        return list(self.pollers.keys())
    
    def get_poller_status(self) -> Dict[str, Dict]:
        """Get status information for all pollers."""
        status = {}
        for ups_name, poller in self.pollers.items():
            status[ups_name] = {
                "is_running": not (poller._task is None or poller._task.done()),
                "last_heartbeat": poller.last_heartbeat,
                "is_disconnected": poller.is_disconnected,
            }
        return status