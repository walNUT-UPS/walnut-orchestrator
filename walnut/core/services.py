"""
Service lifecycle management.

This module provides a simple service manager for starting and stopping
background services like the NUT poller.
"""

import asyncio
import logging
from typing import List, Protocol

logger = logging.getLogger(__name__)


class Service(Protocol):
    """
    A protocol for long-running services that can be started and stopped.
    """
    async def start(self):
        ...

    async def stop(self):
        ...


class ServiceManager:
    """
    Manages the lifecycle of registered services.
    """

    def __init__(self):
        self._services: List[Service] = []

    def register(self, service: Service):
        """
        Register a service to be managed.

        Args:
            service: The service instance to register.
        """
        self._services.append(service)
        logger.info(f"Registered service: {service.__class__.__name__}")

    async def start_all(self):
        """
        Start all registered services concurrently.
        """
        if not self._services:
            logger.info("No services to start.")
            return

        logger.info("Starting all registered services...")
        start_tasks = [
            asyncio.create_task(service.start()) for service in self._services
        ]
        await asyncio.gather(*start_tasks)
        logger.info("All services started.")

    async def stop_all(self):
        """
        Stop all registered services concurrently.
        """
        if not self._services:
            logger.info("No services to stop.")
            return

        logger.info("Stopping all registered services...")
        stop_tasks = [
            asyncio.create_task(service.stop()) for service in self._services
        ]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        logger.info("All services stopped.")
