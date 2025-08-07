"""
Host management module for walNUT UPS Management Platform.

Provides host configuration, discovery, and management capabilities
for coordinated shutdown operations.
"""

from walnut.hosts.manager import HostManager, HostDiscovery

__all__ = ["HostManager", "HostDiscovery"]