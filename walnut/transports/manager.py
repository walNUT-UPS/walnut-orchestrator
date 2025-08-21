"""
Transport Manager

This module provides a manager class that handles the lifecycle of transport
adapter instances for a given integration instance.
"""

import asyncio
from typing import Dict, Any, Optional

from .base import TransportAdapter
from .registry import get as get_transport


class TransportManager:
    """
    Manages transport adapter instances for a single integration instance.

    It lazy-loads and prepares adapters on demand, ensuring that each transport
    (http, ssh, etc.) is initialized only once per manager instance.
    """

    def __init__(self, instance_config: Dict[str, Any]):
        """
        Initializes the manager with the configuration of a specific
        integration instance.

        Args:
            instance_config: The 'config' dictionary from an IntegrationInstance.
        """
        self._instance_config = instance_config
        self._adapters: Dict[str, TransportAdapter] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> TransportAdapter:
        """
        Gets a prepared transport adapter by name (e.g., 'http', 'ssh').

        If the adapter has not been used yet, it will be instantiated,
        prepared with the relevant configuration, and cached for future use.
        """
        # Default to 'http' for backward compatibility if name is not provided.
        name = name or "http"

        async with self._lock:
            if name not in self._adapters:
                # 1. Get the adapter *instance* from the registry
                adapter = get_transport(name)

                # 2. Get the transport-specific config block if it exists
                # e.g., instance_config.transports.ssh
                transport_defaults = self._instance_config.get("defaults", {}).get("transports", {})
                transport_cfg = transport_defaults.get(name, {})

                # 3. For backward compatibility, merge top-level config.
                # This allows old configs without a 'transports' block to work,
                # and also makes top-level keys available to all transports.
                merged_cfg = {**self._instance_config, **transport_cfg}

                # 4. Prepare the adapter with the combined configuration.
                await adapter.prepare(merged_cfg)
                self._adapters[name] = adapter

            return self._adapters[name]

    async def close_all(self):
        """
        Closes all managed transport adapters that have been initialized.
        """
        for adapter in self._adapters.values():
            try:
                await adapter.close()
            except Exception as e:
                # Log error but continue trying to close others
                print(f"Error closing adapter {adapter.name}: {e}")

        self._adapters.clear()
