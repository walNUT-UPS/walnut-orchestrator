"""
Background polling service for NUT integration.

This module contains the NUTPoller class, which is responsible for
periodically polling a NUT server, storing the data, and generating
events based on status changes.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from ..config import settings
from ..database.connection import get_db_transaction
from ..database.models import UPSSample, create_event, create_ups_sample
from .client import NUTClient, NUTConnectionError
from .events import detect_events
from .models import UPSData
from ..core.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class NUTPoller:
    """
    A service that polls a NUT server for UPS data.
    """

    def __init__(self, ups_name: str):
        """
        Initialize the NUT poller.

        Args:
            ups_name: The name of the UPS to poll.
        """
        self.ups_name = ups_name
        self.client = NUTClient()
        self._task: asyncio.Task | None = None
        self._should_stop = asyncio.Event()
        self.last_heartbeat: float = 0.0
        self.previous_data: UPSData | None = None
        self.last_cleanup_time: float = 0.0
        self.is_disconnected = False

    async def start(self):
        """Start the poller as a background task."""
        if self._task and not self._task.done():
            logger.warning("Poller is already running.")
            return

        logger.info(f"Starting NUT poller for UPS '{self.ups_name}'")
        self._should_stop.clear()
        self.last_heartbeat = time.time()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop the poller."""
        if not self._task or self._task.done():
            logger.warning("Poller is not running.")
            return

        logger.info(f"Stopping NUT poller for UPS '{self.ups_name}'")
        self._should_stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.error("Poller task did not stop gracefully within timeout.")
            self._task.cancel()
        logger.info("NUT poller stopped.")

    async def _poll_loop(self):
        """The main polling loop."""
        while not self._should_stop.is_set():
            try:
                ups_vars = await asyncio.wait_for(
                    self.client.get_vars(self.ups_name),
                    timeout=10.0
                )

                if self.is_disconnected:
                    logger.info("Reconnected to NUT server.")
                    self.is_disconnected = False

                self.last_heartbeat = time.time()
                current_data = UPSData.model_validate(ups_vars, from_attributes=True)

                await self._process_data(current_data)
                
                # Broadcast UPS status via WebSocket
                await self._broadcast_ups_status(current_data)
                
                self.previous_data = current_data

                if time.time() - self.last_cleanup_time > 3600:  # Every hour
                    await self._cleanup_old_data()

            except NUTConnectionError as e:
                logger.error(f"Failed to connect to NUT server: {e}")
            except asyncio.TimeoutError:
                logger.error("Timeout when polling NUT server.")
            except Exception:
                logger.exception("An unexpected error occurred in the polling loop.")

            await self._check_heartbeat()

            try:
                await asyncio.sleep(settings.POLL_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _process_data(self, current_data: UPSData):
        """Process and store a new data sample."""
        try:
            async with get_db_transaction() as session:
                sample = create_ups_sample(
                    charge_percent=current_data.battery_charge,
                    runtime_seconds=current_data.battery_runtime,
                    load_percent=current_data.ups_load,
                    input_voltage=current_data.input_voltage,
                    output_voltage=current_data.output_voltage,
                    status=current_data.status,
                )
                session.add(sample)

                events = detect_events(self.previous_data, current_data)
                for event_type in events:
                    description = f"Event '{event_type}' detected for UPS '{self.ups_name}'"
                    event = create_event(
                        event_type=event_type,
                        description=description,
                        severity="WARNING",
                    )
                    session.add(event)
                    logger.warning(f"Generated event: {event_type} for UPS '{self.ups_name}'")
                    
                    # Broadcast event via WebSocket
                    await self._broadcast_event(event_type, current_data)
        except Exception:
            logger.exception("Failed to process and store UPS data.")

    async def _check_heartbeat(self):
        """Check for NUT server heartbeat timeout."""
        if time.time() - self.last_heartbeat > settings.HEARTBEAT_TIMEOUT:
            if not self.is_disconnected:
                logger.critical(f"NUT server heartbeat timeout for UPS '{self.ups_name}'. Connection lost.")
                self.is_disconnected = True
                try:
                    async with get_db_transaction() as session:
                        event = create_event(
                            event_type="NUT_SERVER_LOST",
                            description=f"Connection to NUT server for UPS '{self.ups_name}' lost (heartbeat timeout).",
                            severity="CRITICAL",
                        )
                        session.add(event)
                        
                        # Broadcast critical connection lost event
                        await websocket_manager.broadcast_event(
                            "NUT_SERVER_LOST",
                            {
                                "ups_name": self.ups_name,
                                "description": f"Connection to NUT server for UPS '{self.ups_name}' lost"
                            },
                            "CRITICAL"
                        )
                except Exception:
                    logger.exception("Failed to store NUT server lost event.")

    async def _cleanup_old_data(self):
        """Delete UPS samples older than the retention period."""
        logger.info("Cleaning up old UPS samples...")
        self.last_cleanup_time = time.time()
        try:
            async with get_db_transaction() as session:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=settings.DATA_RETENTION_HOURS)
                stmt = delete(UPSSample).where(UPSSample.timestamp < cutoff_time)
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info(f"Deleted {result.rowcount} old UPS samples.")
        except Exception:
            logger.exception("Failed to clean up old UPS data.")
    
    async def _broadcast_ups_status(self, ups_data: UPSData):
        """
        Broadcast UPS status update via WebSocket.
        
        Args:
            ups_data: Current UPS data to broadcast
        """
        try:
            # Convert UPS data to dictionary format for WebSocket broadcast
            status_data = {
                "ups_name": self.ups_name,
                "battery_percent": ups_data.battery_charge,
                "runtime_seconds": ups_data.battery_runtime,
                "load_percent": ups_data.ups_load,
                "input_voltage": ups_data.input_voltage,
                "output_voltage": ups_data.output_voltage,
                "status": ups_data.status,
                "timestamp": time.time()
            }
            
            # Broadcast via WebSocket manager
            await websocket_manager.broadcast_ups_status(status_data)
            
        except Exception as e:
            logger.error(f"Failed to broadcast UPS status: {e}")
    
    async def _broadcast_event(self, event_type: str, ups_data: UPSData):
        """
        Broadcast power event via WebSocket.
        
        Args:
            event_type: Type of event that occurred
            ups_data: Current UPS data context
        """
        try:
            event_data = {
                "ups_name": self.ups_name,
                "event_type": event_type,
                "description": f"Event '{event_type}' detected for UPS '{self.ups_name}'",
                "battery_percent": ups_data.battery_charge,
                "status": ups_data.status,
                "timestamp": time.time()
            }
            
            # Determine severity based on event type
            severity = "CRITICAL" if event_type in ["MAINS_LOST", "LOW_BATTERY"] else "WARNING"
            
            # Broadcast via WebSocket manager
            await websocket_manager.broadcast_event(event_type, event_data, severity)
            
        except Exception as e:
            logger.error(f"Failed to broadcast event {event_type}: {e}")
