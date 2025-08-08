"""
Shutdown orchestration module for walNUT UPS Management Platform.

Provides coordinated shutdown capabilities for hosts during power events,
with immediate execution, timeout handling, and comprehensive logging.
"""

from walnut.shutdown.executor import ShutdownExecutor, ShutdownResult
from walnut.shutdown.triggers import ShutdownTrigger, UPSEventTrigger

__all__ = ["ShutdownExecutor", "ShutdownResult", "ShutdownTrigger", "UPSEventTrigger"]