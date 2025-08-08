"""
Event-based shutdown triggers for UPS power events.

Monitors UPS status changes and automatically triggers shutdown sequences
when specific conditions are met (like OnBattery status).
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from walnut.database.connection import get_db_session
from walnut.database.models import UPSSample, create_event
from walnut.shutdown.executor import ShutdownExecutor

logger = logging.getLogger(__name__)


class TriggerCondition(Enum):
    """UPS conditions that can trigger shutdowns."""
    ON_BATTERY = "OB"  # UPS switched to battery power
    LOW_BATTERY = "LB"  # Battery charge is low
    REPLACE_BATTERY = "RB"  # Battery needs replacement
    CRITICAL_LOAD = "OVER"  # UPS overload condition
    COMMUNICATIONS_LOST = "COMM_LOST"  # Lost contact with UPS


@dataclass
class TriggerConfig:
    """Configuration for shutdown triggers."""
    
    condition: TriggerCondition
    enabled: bool = True
    
    # Immediate vs delayed shutdown
    immediate: bool = True
    delay_seconds: float = 0.0
    
    # Target hosts (empty = all hosts)
    target_hosts: List[str] = None
    exclude_hosts: List[str] = None
    
    # Conditions for trigger activation
    min_battery_charge: Optional[float] = None  # Only trigger if battery below this %
    max_runtime_seconds: Optional[int] = None   # Only trigger if runtime below this
    
    # Retry and timeout settings
    timeout_seconds: int = 60
    max_retries: int = 2
    
    # Custom shutdown command
    shutdown_command: Optional[str] = None
    
    def __post_init__(self):
        if self.target_hosts is None:
            self.target_hosts = []
        if self.exclude_hosts is None:
            self.exclude_hosts = []


class ShutdownTrigger(ABC):
    """Abstract base class for shutdown triggers."""
    
    def __init__(self, config: TriggerConfig, executor: Optional[ShutdownExecutor] = None):
        self.config = config
        self.executor = executor or ShutdownExecutor()
        self._active = False
        self._triggered_at: Optional[datetime] = None
        self._last_status: Optional[str] = None
    
    @abstractmethod
    async def should_trigger(self, **kwargs) -> bool:
        """Check if trigger conditions are met."""
        pass
    
    @abstractmethod
    async def get_trigger_data(self) -> Dict[str, Any]:
        """Get current trigger data for evaluation."""
        pass
    
    async def evaluate_and_trigger(self, **kwargs) -> bool:
        """
        Evaluate trigger conditions and execute shutdown if needed.
        
        Returns:
            True if shutdown was triggered, False otherwise
        """
        if not self.config.enabled:
            return False
        
        try:
            should_trigger = await self.should_trigger(**kwargs)
            
            if should_trigger and not self._active:
                logger.warning(f"Shutdown trigger activated: {self.config.condition.value}")
                
                # Mark as active to prevent duplicate triggers
                self._active = True
                self._triggered_at = datetime.now(timezone.utc)
                
                # Log trigger event
                await self._log_trigger_event("TRIGGER_ACTIVATED", kwargs)
                
                # Execute shutdown (with optional delay)
                if self.config.delay_seconds > 0:
                    logger.info(f"Delaying shutdown by {self.config.delay_seconds} seconds")
                    await asyncio.sleep(self.config.delay_seconds)
                
                return await self._execute_shutdown()
            
            elif not should_trigger and self._active:
                # Condition no longer met, deactivate trigger
                logger.info(f"Shutdown trigger deactivated: {self.config.condition.value}")
                self._active = False
                self._triggered_at = None
                await self._log_trigger_event("TRIGGER_DEACTIVATED", kwargs)
        
        except Exception as e:
            logger.error(f"Error evaluating trigger {self.config.condition.value}: {e}")
            await self._log_trigger_event("TRIGGER_ERROR", kwargs, error=str(e))
        
        return False
    
    async def _execute_shutdown(self) -> bool:
        """Execute the configured shutdown operation."""
        try:
            # Determine target hosts
            target_hosts = await self._get_target_hosts()
            
            if not target_hosts:
                logger.warning("No target hosts found for shutdown trigger")
                return False
            
            logger.critical(f"Executing emergency shutdown on {len(target_hosts)} hosts")
            
            # Execute shutdown
            results = await self.executor.execute_mass_shutdown(
                hostnames=target_hosts,
                command=self.config.shutdown_command,
                timeout=self.config.timeout_seconds,
                max_concurrent=10,  # High concurrency for emergency
            )
            
            # Check results
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            
            logger.critical(
                f"Emergency shutdown completed: {successful} successful, {failed} failed"
            )
            
            # Log results
            await self._log_trigger_event(
                "SHUTDOWN_EXECUTED",
                {
                    'total_hosts': len(target_hosts),
                    'successful': successful,
                    'failed': failed,
                    'results': [r.to_dict() for r in results[:10]]  # Limit logged results
                }
            )
            
            return successful > 0
        
        except Exception as e:
            logger.error(f"Failed to execute trigger shutdown: {e}")
            await self._log_trigger_event("SHUTDOWN_FAILED", {}, error=str(e))
            return False
    
    async def _get_target_hosts(self) -> List[str]:
        """Get list of target hosts for shutdown."""
        # If specific hosts are configured, use those
        if self.config.target_hosts:
            # Remove excluded hosts
            return [
                host for host in self.config.target_hosts 
                if host not in self.config.exclude_hosts
            ]
        
        # Otherwise, get all SSH hosts and exclude the configured ones
        from walnut.hosts.manager import HostManager
        host_manager = HostManager()
        
        hosts = await host_manager.list_hosts(connection_type="ssh")
        return [
            host.hostname for host in hosts
            if host.hostname not in self.config.exclude_hosts
        ]
    
    async def _log_trigger_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        error: Optional[str] = None,
    ):
        """Log trigger event to database."""
        try:
            async with get_db_session() as session:
                metadata = {
                    'trigger_condition': self.config.condition.value,
                    'trigger_config': {
                        'immediate': self.config.immediate,
                        'delay_seconds': self.config.delay_seconds,
                        'target_hosts': self.config.target_hosts,
                        'exclude_hosts': self.config.exclude_hosts,
                    },
                    'trigger_data': data,
                    'triggered_at': self._triggered_at.isoformat() if self._triggered_at else None,
                }
                
                if error:
                    metadata['error'] = error
                
                severity = "CRITICAL" if event_type.startswith("SHUTDOWN") else "WARNING"
                description = f"Shutdown trigger {event_type}: {self.config.condition.value}"
                
                event = create_event(
                    event_type=event_type,
                    description=description,
                    severity=severity,
                    metadata=metadata,
                )
                
                session.add(event)
                await session.commit()
        
        except Exception as e:
            logger.error(f"Failed to log trigger event: {e}")
    
    def is_active(self) -> bool:
        """Check if trigger is currently active."""
        return self._active
    
    def get_status(self) -> Dict[str, Any]:
        """Get trigger status information."""
        return {
            'condition': self.config.condition.value,
            'enabled': self.config.enabled,
            'active': self._active,
            'triggered_at': self._triggered_at.isoformat() if self._triggered_at else None,
            'immediate': self.config.immediate,
            'delay_seconds': self.config.delay_seconds,
            'target_hosts': len(self.config.target_hosts),
            'exclude_hosts': len(self.config.exclude_hosts),
        }


class UPSEventTrigger(ShutdownTrigger):
    """
    Triggers shutdown based on UPS status changes and conditions.
    
    Monitors UPS samples for status changes like OnBattery (OB) and
    triggers immediate shutdown based on configuration.
    """
    
    def __init__(
        self,
        config: TriggerConfig,
        executor: Optional[ShutdownExecutor] = None,
        nut_client: Optional[Any] = None,  # Will be PyNUT2 client when available
    ):
        super().__init__(config, executor)
        self.nut_client = nut_client
        
        # Cache for recent UPS data
        self._last_sample: Optional[UPSSample] = None
        self._status_history: List[Tuple[datetime, str]] = []
    
    async def get_latest_ups_sample(self) -> Optional[UPSSample]:
        """Get the most recent UPS sample from database."""
        try:
            from sqlalchemy import select
            
            async with get_db_session() as session:
                result = await session.execute(
                    select(UPSSample)
                    .order_by(UPSSample.timestamp.desc())
                    .limit(1)
                )
                return result.scalar_one_or_none()
        
        except Exception as e:
            logger.error(f"Failed to get latest UPS sample: {e}")
            return None
    
    async def get_trigger_data(self) -> Dict[str, Any]:
        """Get current UPS data for trigger evaluation."""
        sample = await self.get_latest_ups_sample()
        
        if not sample:
            return {}
        
        return {
            'timestamp': sample.timestamp.isoformat(),
            'status': sample.status,
            'charge_percent': sample.charge_percent,
            'runtime_seconds': sample.runtime_seconds,
            'load_percent': sample.load_percent,
            'input_voltage': sample.input_voltage,
            'output_voltage': sample.output_voltage,
        }
    
    async def should_trigger(self, **kwargs) -> bool:
        """
        Check if UPS conditions warrant a shutdown trigger.
        
        Args:
            **kwargs: Additional context data
            
        Returns:
            True if shutdown should be triggered
        """
        sample = await self.get_latest_ups_sample()
        
        if not sample or not sample.status:
            return False
        
        # Update status history
        now = datetime.now(timezone.utc)
        self._status_history.append((now, sample.status))
        
        # Keep only recent history (last 10 minutes)
        cutoff = now.timestamp() - 600
        self._status_history = [
            (ts, status) for ts, status in self._status_history
            if ts.timestamp() > cutoff
        ]
        
        # Check primary trigger condition
        status_matches = self._check_status_condition(sample.status)
        
        if not status_matches:
            return False
        
        # Check additional conditions
        if not self._check_battery_conditions(sample):
            return False
        
        # Check if this is a new trigger (avoid re-triggering)
        if self._is_status_change(sample.status):
            logger.warning(f"UPS status changed to: {sample.status}")
            return True
        
        # Already triggered for this status
        return False
    
    def _check_status_condition(self, status: str) -> bool:
        """Check if UPS status matches trigger condition."""
        if self.config.condition == TriggerCondition.ON_BATTERY:
            # Trigger on OnBattery status (OB, OB LB, etc.)
            return "OB" in status.upper()
        
        elif self.config.condition == TriggerCondition.LOW_BATTERY:
            return "LB" in status.upper()
        
        elif self.config.condition == TriggerCondition.REPLACE_BATTERY:
            return "RB" in status.upper()
        
        elif self.config.condition == TriggerCondition.CRITICAL_LOAD:
            return "OVER" in status.upper()
        
        return False
    
    def _check_battery_conditions(self, sample: UPSSample) -> bool:
        """Check additional battery-related conditions."""
        # Check minimum battery charge
        if (self.config.min_battery_charge is not None and 
            sample.charge_percent is not None):
            if sample.charge_percent > self.config.min_battery_charge:
                logger.debug(
                    f"Battery charge {sample.charge_percent}% above threshold "
                    f"{self.config.min_battery_charge}%"
                )
                return False
        
        # Check maximum runtime
        if (self.config.max_runtime_seconds is not None and 
            sample.runtime_seconds is not None):
            if sample.runtime_seconds > self.config.max_runtime_seconds:
                logger.debug(
                    f"Runtime {sample.runtime_seconds}s above threshold "
                    f"{self.config.max_runtime_seconds}s"
                )
                return False
        
        return True
    
    def _is_status_change(self, current_status: str) -> bool:
        """Check if this represents a new status change."""
        if self._last_status != current_status:
            self._last_status = current_status
            return True
        return False


class ShutdownTriggerManager:
    """
    Manages multiple shutdown triggers and coordinates their evaluation.
    
    Provides centralized management of triggers with periodic monitoring
    and event-driven evaluation.
    """
    
    def __init__(self, executor: Optional[ShutdownExecutor] = None):
        self.executor = executor or ShutdownExecutor()
        self.triggers: List[ShutdownTrigger] = []
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    def add_trigger(self, trigger: ShutdownTrigger):
        """Add a trigger to the manager."""
        self.triggers.append(trigger)
        logger.info(f"Added shutdown trigger: {trigger.config.condition.value}")
    
    def remove_trigger(self, condition: TriggerCondition) -> bool:
        """Remove trigger by condition type."""
        for i, trigger in enumerate(self.triggers):
            if trigger.config.condition == condition:
                del self.triggers[i]
                logger.info(f"Removed shutdown trigger: {condition.value}")
                return True
        return False
    
    async def evaluate_all_triggers(self) -> List[bool]:
        """
        Evaluate all triggers and return results.
        
        Returns:
            List of trigger results (True if triggered)
        """
        if not self.triggers:
            return []
        
        tasks = [trigger.evaluate_and_trigger() for trigger in self.triggers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and log exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Trigger evaluation failed: {result}")
                processed_results.append(False)
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def start_monitoring(self, interval: float = 5.0):
        """
        Start continuous monitoring of triggers.
        
        Args:
            interval: Monitoring interval in seconds
        """
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        logger.info(f"Started trigger monitoring (interval: {interval}s)")
    
    async def stop_monitoring(self):
        """Stop continuous monitoring."""
        self._monitoring = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        logger.info("Stopped trigger monitoring")
    
    async def _monitor_loop(self, interval: float):
        """Main monitoring loop."""
        logger.info("Trigger monitoring started")
        
        try:
            while self._monitoring:
                try:
                    results = await self.evaluate_all_triggers()
                    
                    # Log if any triggers activated
                    triggered_count = sum(1 for r in results if r)
                    if triggered_count > 0:
                        logger.critical(f"{triggered_count} shutdown triggers activated")
                
                except Exception as e:
                    logger.error(f"Error in trigger monitoring loop: {e}")
                
                # Wait for next interval
                await asyncio.sleep(interval)
        
        except asyncio.CancelledError:
            logger.info("Trigger monitoring cancelled")
        except Exception as e:
            logger.error(f"Trigger monitoring failed: {e}")
        finally:
            logger.info("Trigger monitoring stopped")
    
    def get_trigger_status(self) -> List[Dict[str, Any]]:
        """Get status of all triggers."""
        return [trigger.get_status() for trigger in self.triggers]
    
    def create_immediate_onbattery_trigger(
        self,
        target_hosts: Optional[List[str]] = None,
        exclude_hosts: Optional[List[str]] = None,
    ) -> UPSEventTrigger:
        """
        Create immediate OnBattery shutdown trigger for srv-pbs-01.
        
        Args:
            target_hosts: Specific hosts to target (default: srv-pbs-01)
            exclude_hosts: Hosts to exclude
            
        Returns:
            Configured UPS event trigger
        """
        # Default to srv-pbs-01 as primary target
        if target_hosts is None:
            target_hosts = ["srv-pbs-01"]
        
        config = TriggerConfig(
            condition=TriggerCondition.ON_BATTERY,
            enabled=True,
            immediate=True,
            delay_seconds=0.0,
            target_hosts=target_hosts,
            exclude_hosts=exclude_hosts or [],
            timeout_seconds=60,
            max_retries=2,
            shutdown_command=None,  # Use OS-specific default
        )
        
        trigger = UPSEventTrigger(config, self.executor)
        
        logger.info(f"Created immediate OnBattery trigger for hosts: {target_hosts}")
        return trigger