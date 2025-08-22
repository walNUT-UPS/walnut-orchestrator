"""
Host inventory and capability indexing system.

This module provides fast inventory refresh and capability indexing for policy
target resolution and dry-run operations as specified in POLICY.md.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from walnut.policy.models import (
    HostCapabilities, HostCapability, HostInventory, TargetInfo
)


class InventoryIndex:
    """
    Host inventory and capability index for fast policy operations.
    
    Provides fast refresh capabilities and searchable target indexes
    for policy compilation and execution.
    """

    def __init__(self, integration_manager=None, plugin_registry=None):
        """
        Initialize inventory index.
        
        Args:
            integration_manager: Integration manager for host communication
            plugin_registry: Plugin registry for capability information
        """
        self.integration_manager = integration_manager
        self.plugin_registry = plugin_registry
        self._inventory_cache = {}
        self._capability_cache = {}
        self._last_refresh = {}

    async def get_host_capabilities(self, host_id: UUID) -> HostCapabilities:
        """
        Get host capabilities from integration metadata.
        
        Args:
            host_id: Host UUID
            
        Returns:
            HostCapabilities with available capabilities
            
        Raises:
            ValueError: If host not found
        """
        # Check cache first
        cache_key = str(host_id)
        if cache_key in self._capability_cache:
            cached = self._capability_cache[cache_key]
            # Cache is valid for 5 minutes
            if (datetime.now(timezone.utc) - cached["ts"]) < timedelta(minutes=5):
                return cached["data"]

        # Get host integration info
        if not self.integration_manager:
            raise ValueError(f"Integration manager not available")

        try:
            host_info = await self.integration_manager.get_host_info(host_id)
            if not host_info:
                raise ValueError(f"Host {host_id} not found")

            integration_type = host_info.get("integration_type")
            if not integration_type:
                raise ValueError(f"Host {host_id} has no integration type")

            # Get plugin capabilities
            capabilities = await self._load_plugin_capabilities(integration_type)
            
            result = HostCapabilities(
                host_id=host_id,
                capabilities=capabilities,
                ts=datetime.now(timezone.utc)
            )

            # Cache result
            self._capability_cache[cache_key] = {
                "data": result,
                "ts": datetime.now(timezone.utc)
            }

            return result

        except Exception as e:
            raise ValueError(f"Failed to get host capabilities: {str(e)}")

    async def get_host_inventory(self, host_id: UUID, refresh: bool = False) -> HostInventory:
        """
        Get host inventory with optional fast refresh.
        
        Args:
            host_id: Host UUID
            refresh: Whether to force inventory refresh
            
        Returns:
            HostInventory with discovered targets
            
        Raises:
            ValueError: If host not found or refresh fails
        """
        cache_key = str(host_id)
        
        # Check if refresh is needed
        needs_refresh = refresh
        if not needs_refresh and cache_key in self._inventory_cache:
            cached = self._inventory_cache[cache_key]
            # Consider stale after 30 seconds for fast refresh
            if (datetime.now(timezone.utc) - cached["ts"]) > timedelta(seconds=30):
                needs_refresh = True

        # Perform refresh if needed
        if needs_refresh or cache_key not in self._inventory_cache:
            await self._refresh_host_inventory(host_id)

        # Return cached inventory
        if cache_key in self._inventory_cache:
            cached = self._inventory_cache[cache_key]
            return cached["data"]
        else:
            # Return empty inventory if refresh failed
            return HostInventory(
                host_id=host_id,
                targets=[],
                ts=datetime.now(timezone.utc),
                stale=True
            )

    async def refresh_host_fast(self, host_id: UUID, sla_seconds: int = 5) -> bool:
        """
        Fast refresh of host inventory with SLA timeout.
        
        Args:
            host_id: Host UUID
            sla_seconds: Maximum time to spend on refresh
            
        Returns:
            True if refresh succeeded within SLA
        """
        try:
            await asyncio.wait_for(
                self._refresh_host_inventory(host_id),
                timeout=sla_seconds
            )
            return True
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    async def search_targets(self, host_id: UUID, target_type: str, 
                           query: str = "") -> List[TargetInfo]:
        """
        Search host targets by type and optional query.
        
        Args:
            host_id: Host UUID
            target_type: Target type filter
            query: Optional search query for name/labels
            
        Returns:
            List of matching TargetInfo
        """
        inventory = await self.get_host_inventory(host_id)
        
        # Filter by target type
        targets = [t for t in inventory.targets if target_type in t.id]
        
        # Apply query filter if provided
        if query:
            query_lower = query.lower()
            filtered_targets = []
            for target in targets:
                if (query_lower in target.name.lower() or
                    query_lower in target.friendly.lower() or
                    any(query_lower in str(v).lower() for v in target.labels.values())):
                    filtered_targets.append(target)
            targets = filtered_targets

        return targets

    async def _refresh_host_inventory(self, host_id: UUID):
        """
        Refresh host inventory from integration discovery.
        
        Args:
            host_id: Host UUID to refresh
        """
        if not self.integration_manager:
            raise ValueError("Integration manager not available")

        try:
            # Get host info
            host_info = await self.integration_manager.get_host_info(host_id)
            if not host_info:
                raise ValueError(f"Host {host_id} not found")

            integration_instance = host_info.get("integration_instance")
            if not integration_instance:
                raise ValueError(f"Host {host_id} has no integration instance")

            # Get driver for discovery
            driver = await self.integration_manager.get_driver(integration_instance)
            if not driver:
                raise ValueError(f"No driver available for host {host_id}")

            # Perform fast discovery
            discovery_result = await driver.discover_targets(fast=True)
            
            # Convert to TargetInfo format
            targets = []
            for target_data in discovery_result.get("targets", []):
                target_info = TargetInfo(
                    id=target_data.get("canonical_id", target_data.get("id")),
                    name=target_data.get("name", ""),
                    labels=target_data.get("labels", {}),
                    friendly=target_data.get("friendly_name", target_data.get("name", ""))
                )
                targets.append(target_info)

            # Create inventory result
            inventory = HostInventory(
                host_id=host_id,
                targets=targets,
                ts=datetime.now(timezone.utc),
                stale=False
            )

            # Cache result
            cache_key = str(host_id)
            self._inventory_cache[cache_key] = {
                "data": inventory,
                "ts": datetime.now(timezone.utc)
            }
            self._last_refresh[cache_key] = datetime.now(timezone.utc)

        except Exception as e:
            # Mark cache as stale on error
            cache_key = str(host_id)
            if cache_key in self._inventory_cache:
                cached = self._inventory_cache[cache_key]
                cached["data"].stale = True
            raise ValueError(f"Failed to refresh host inventory: {str(e)}")

    async def _load_plugin_capabilities(self, integration_type: str) -> List[HostCapability]:
        """
        Load capabilities from plugin metadata.
        
        Args:
            integration_type: Integration type ID
            
        Returns:
            List of HostCapability objects
        """
        if not self.plugin_registry:
            return []

        try:
            plugin_info = self.plugin_registry.get_plugin_info(integration_type)
            if not plugin_info:
                return []

            plugin_capabilities = plugin_info.get("capabilities", [])
            capabilities = []

            for cap_info in plugin_capabilities:
                capability = HostCapability(
                    id=cap_info.get("id", ""),
                    verbs=cap_info.get("verbs", []),
                    invertible=cap_info.get("invertible", {}),
                    idempotency=cap_info.get("idempotency"),
                    dry_run=cap_info.get("dry_run", True)
                )
                capabilities.append(capability)

            return capabilities

        except Exception:
            return []

    def get_cached_inventory_age(self, host_id: UUID) -> Optional[float]:
        """
        Get age of cached inventory in seconds.
        
        Args:
            host_id: Host UUID
            
        Returns:
            Age in seconds, or None if not cached
        """
        cache_key = str(host_id)
        if cache_key not in self._inventory_cache:
            return None

        cached_ts = self._inventory_cache[cache_key]["ts"]
        return (datetime.now(timezone.utc) - cached_ts).total_seconds()

    def clear_cache(self, host_id: Optional[UUID] = None):
        """
        Clear inventory cache.
        
        Args:
            host_id: Specific host to clear, or None for all
        """
        if host_id:
            cache_key = str(host_id)
            self._inventory_cache.pop(cache_key, None)
            self._capability_cache.pop(cache_key, None)
            self._last_refresh.pop(cache_key, None)
        else:
            self._inventory_cache.clear()
            self._capability_cache.clear()
            self._last_refresh.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            "inventory_entries": len(self._inventory_cache),
            "capability_entries": len(self._capability_cache),
            "oldest_inventory": min(
                (datetime.now(timezone.utc) - cached["ts"]).total_seconds()
                for cached in self._inventory_cache.values()
            ) if self._inventory_cache else 0,
            "newest_inventory": max(
                (datetime.now(timezone.utc) - cached["ts"]).total_seconds()
                for cached in self._inventory_cache.values()
            ) if self._inventory_cache else 0,
        }


# Utility functions

def create_inventory_index(integration_manager=None, plugin_registry=None) -> InventoryIndex:
    """
    Create configured inventory index.
    
    Args:
        integration_manager: Integration manager instance
        plugin_registry: Plugin registry instance
        
    Returns:
        Configured InventoryIndex
    """
    return InventoryIndex(integration_manager, plugin_registry)


async def quick_capability_check(host_id: UUID, capability_id: str, verb: str,
                                inventory_index: InventoryIndex) -> bool:
    """
    Quick check if host supports capability and verb.
    
    Args:
        host_id: Host UUID
        capability_id: Capability identifier
        verb: Action verb
        inventory_index: Inventory index instance
        
    Returns:
        True if capability/verb is supported
    """
    try:
        capabilities = await inventory_index.get_host_capabilities(host_id)
        for capability in capabilities.capabilities:
            if capability.id == capability_id:
                return verb in capability.verbs
        return False
    except Exception:
        return False


async def resolve_target_selector(host_id: UUID, target_type: str, selector_value: str,
                                 inventory_index: InventoryIndex) -> List[str]:
    """
    Resolve target selector to canonical IDs.
    
    Args:
        host_id: Host UUID
        target_type: Target type
        selector_value: Selector pattern
        inventory_index: Inventory index instance
        
    Returns:
        List of canonical target IDs
    """
    try:
        targets = await inventory_index.search_targets(host_id, target_type)
        
        # Simple resolution logic - expand based on selector patterns
        if "," in selector_value:
            # List selector
            items = [item.strip() for item in selector_value.split(",")]
            resolved = []
            for item in items:
                for target in targets:
                    if target.name == item or item in target.id:
                        resolved.append(target.id)
            return resolved
            
        elif "-" in selector_value:
            # Range selector (simplified)
            return [t.id for t in targets[:5]]  # Placeholder
            
        else:
            # Single target
            for target in targets:
                if target.name == selector_value or selector_value in target.id:
                    return [target.id]
            return []
            
    except Exception:
        return []