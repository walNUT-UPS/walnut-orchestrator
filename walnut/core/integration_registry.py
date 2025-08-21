"""
Integration Type Registry and Validation Pipeline.

This module handles discovery, validation, and registration of integration types
from the ./integrations/<slug>/ filesystem structure according to the walNUT
integrations architecture specification.
"""

import asyncio
import importlib.util
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import yaml
import logging
import anyio
from sqlalchemy import select

from walnut.database.connection import get_db_session
from walnut.database.models import IntegrationType
from walnut.core.plugin_schema import validate_plugin_manifest, validate_capability_conformance
from walnut.core.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class IntegrationDiscoveryError(Exception):
    """Raised when integration discovery fails."""
    pass


class IntegrationValidationError(Exception):
    """Raised when integration validation fails."""
    pass


class IntegrationTypeRegistry:
    """
    Manages discovery, validation, and registration of integration types.
    
    Implements the three-stage validation pipeline:
    - Stage A: Discovery - scan filesystem and create type records
    - Stage B: Validation - validate manifests, drivers, and conformance
    - Stage C: Result - update status and notify via WebSocket
    """
    
    def __init__(self, integrations_path: str = "./integrations", websocket_manager: Optional[WebSocketManager] = None):
        self.integrations_path = Path(integrations_path).resolve()
        self.websocket_manager = websocket_manager
        self._validation_lock = asyncio.Lock()

    async def ensure_type_record(self, type_id: str, type_path: Path, manifest_data: Dict[str, Any]) -> None:
        """
        Ensure an IntegrationType DB record exists for the given folder/manifest.

        Creates or updates the record with status='checking' without rescanning
        other integrations. Intended for use immediately after an upload installs
        a new integration into the filesystem.
        """
        async with get_db_session() as session:
            def _upsert_sync():
                it = session.query(IntegrationType).filter(IntegrationType.id == type_id).first()
                if it is None:
                    it = IntegrationType(
                        id=type_id,
                        name=manifest_data.get("name", type_id),
                        version=manifest_data.get("version", "0.0.0"),
                        min_core_version=manifest_data.get("min_core_version", "0.1.0"),
                        category=manifest_data.get("category", "unknown"),
                        path=str(type_path),
                        status="checking",
                        capabilities=manifest_data.get("capabilities", []),
                        schema_connection=manifest_data.get("schema", {}).get("connection", {}),
                        driver_entrypoint=manifest_data.get("driver", {}).get("entrypoint", ""),
                    )
                    session.add(it)
                else:
                    it.name = manifest_data.get("name", it.name)
                    it.version = manifest_data.get("version", it.version)
                    it.min_core_version = manifest_data.get("min_core_version", it.min_core_version)
                    it.category = manifest_data.get("category", it.category)
                    it.path = str(type_path)
                    it.status = "checking"
                    it.capabilities = manifest_data.get("capabilities", it.capabilities or [])
                    it.schema_connection = manifest_data.get("schema", {}).get("connection", it.schema_connection or {})
                    it.driver_entrypoint = manifest_data.get("driver", {}).get("entrypoint", it.driver_entrypoint or "")
                session.commit()
                return it

            it = await anyio.to_thread.run_sync(_upsert_sync)
            # Notify subscribers that a new/updated type is now checking
            if self.websocket_manager and it:
                await self.websocket_manager.broadcast_json({
                    "type": "integration_type.updated",
                    "data": {
                        "id": type_id,
                        "status": "checking",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })
    
    async def discover_and_validate_all(self, force_rescan: bool = False) -> Dict[str, Any]:
        """
        Run the complete discovery and validation pipeline.
        
        Args:
            force_rescan: Whether to force rescan even if types exist
            
        Returns:
            Summary of discovery and validation results
        """
        async with self._validation_lock:
            logger.info(f"Starting integration discovery from {self.integrations_path}")
            
            # Stage A: Discovery
            discovered_types = await self._discover_integration_types()
            logger.info(f"Discovered {len(discovered_types)} integration folders")
            
            # Stage B: Validation (async per folder)
            validation_tasks = []
            for type_data in discovered_types:
                task = asyncio.create_task(
                    self._validate_integration_type(type_data),
                    name=f"validate-{type_data['id']}"
                )
                validation_tasks.append(task)
            
            # Wait for all validations to complete
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
            
            # Stage C: Results summary
            valid_count = 0
            invalid_count = 0
            error_count = 0
            
            for result in validation_results:
                if isinstance(result, Exception):
                    error_count += 1
                    logger.error(f"Validation task failed: {result}")
                elif result and result.get("status") == "valid":
                    valid_count += 1
                else:
                    invalid_count += 1
            
            summary = {
                "discovered": len(discovered_types),
                "valid": valid_count,
                "invalid": invalid_count,
                "errors": error_count,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"Discovery complete: {summary}")
            return summary
    
    async def _discover_integration_types(self) -> List[Dict[str, Any]]:
        """
        Stage A: Discover integration types from filesystem.
        
        Scans ./integrations/<slug>/ for plugin.yaml files and creates
        initial type records with status=checking.
        """
        discovered_types = []
        
        if not self.integrations_path.exists():
            logger.warning(f"Integrations path does not exist: {self.integrations_path}")
            return []
        
        async with get_db_session() as session:
            # Use sync database operations wrapped in anyio.to_thread.run_sync
            def _discovery_sync_operations():
                # Get existing types to track what needs cleanup
                existing_types = {t.id: t for t in session.query(IntegrationType).all()}
                found_type_ids = set()
                sync_discovered_types = []
                
                for folder_path in self.integrations_path.iterdir():
                    if not folder_path.is_dir():
                        continue
                    
                    plugin_yaml_path = folder_path / "plugin.yaml"
                    if not plugin_yaml_path.exists():
                        logger.debug(f"Skipping {folder_path.name}: no plugin.yaml found")
                        continue
                    
                    try:
                        # Read and parse manifest
                        with open(plugin_yaml_path, 'r') as f:
                            manifest_data = yaml.safe_load(f)
                        
                        if not manifest_data or not isinstance(manifest_data, dict):
                            logger.warning(f"Invalid YAML in {plugin_yaml_path}")
                            continue
                        
                        type_id = manifest_data.get("id")
                        if not type_id:
                            logger.warning(f"No 'id' field in {plugin_yaml_path}")
                            continue
                        
                        found_type_ids.add(type_id)
                        
                        # Create or update type record with checking status
                        if type_id in existing_types:
                            integration_type = existing_types[type_id]
                            integration_type.status = "checking"
                            integration_type.path = str(folder_path)
                        else:
                            integration_type = IntegrationType(
                                id=type_id,
                                name=manifest_data.get("name", folder_path.name),
                                version=manifest_data.get("version", "0.0.0"),
                                min_core_version=manifest_data.get("min_core_version", "0.1.0"),
                                category=manifest_data.get("category", "unknown"),
                                path=str(folder_path),
                                status="checking",
                                capabilities=[],
                                schema_connection={},
                                driver_entrypoint=manifest_data.get("driver", {}).get("entrypoint", ""),
                            )
                            session.add(integration_type)
                        
                        sync_discovered_types.append({
                            "id": type_id,
                            "path": str(folder_path),
                            "manifest_data": manifest_data
                        })
                    
                    except Exception as e:
                        logger.error(f"Error processing {folder_path}: {e}")
                        continue
                
                # Mark missing types as unavailable
                for type_id, integration_type in existing_types.items():
                    if type_id not in found_type_ids:
                        integration_type.status = "unavailable"
                        logger.info(f"Marked integration type {type_id} as unavailable")
                
                session.commit()
                return sync_discovered_types
            
            # Run discovery sync operations in thread
            discovered_types = await anyio.to_thread.run_sync(_discovery_sync_operations)
            
            # Notify WebSocket clients about status changes (async operations outside of sync)
            if self.websocket_manager:
                for type_data in discovered_types:
                    await self.websocket_manager.broadcast_json({
                        "type": "integration_type.updated",
                        "data": {
                            "id": type_data["id"],
                            "status": "checking",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
        
        return discovered_types
    
    async def _validate_integration_type(self, type_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage B: Validate a single integration type.
        
        Runs the complete validation pipeline for one integration:
        1. Schema validation of plugin.yaml
        2. Driver file existence check  
        3. Driver import and method conformance
        4. Core version compatibility
        """
        type_id = type_data["id"]
        type_path = Path(type_data["path"])
        manifest_data = type_data["manifest_data"]
        
        logger.info(f"Validating integration type: {type_id}")
        
        validation_result = {
            "id": type_id,
            "status": "valid",
            "errors": {}
        }
        
        try:
            # Step 1: Validate plugin.yaml schema
            schema_validation = validate_plugin_manifest(manifest_data)
            if not schema_validation["valid"]:
                validation_result["status"] = "invalid"
                validation_result["errors"]["schema_error"] = schema_validation["errors"]
                logger.warning(f"{type_id}: Schema validation failed")
            
            # Step 2: Check driver.py exists
            driver_path = type_path / "driver.py"
            if not driver_path.exists():
                validation_result["status"] = "invalid"
                validation_result["errors"]["driver_missing"] = f"Driver file not found: {driver_path}"
                logger.warning(f"{type_id}: Driver file missing")
            
            # Step 3: Import driver and validate conformance
            if validation_result["status"] == "valid":
                try:
                    driver_class, driver_methods = await self._import_and_inspect_driver(
                        type_path, manifest_data["driver"]["entrypoint"]
                    )
                    
                    # Check capability conformance (Option A)
                    capabilities = manifest_data.get("capabilities", [])
                    conformance_result = validate_capability_conformance(capabilities, driver_methods)
                    
                    if not conformance_result["conformant"]:
                        validation_result["status"] = "invalid"
                        validation_result["errors"]["capability_mismatch"] = conformance_result["errors"]
                        logger.warning(f"{type_id}: Capability conformance failed")
                    
                    # Verify test_connection method exists
                    if "test_connection" not in driver_methods:
                        validation_result["status"] = "invalid"
                        validation_result["errors"]["missing_test_connection"] = "Driver must implement test_connection() method"
                        logger.warning(f"{type_id}: Missing test_connection method")
                
                except Exception as e:
                    import traceback as _tb
                    validation_result["status"] = "invalid"
                    validation_result["errors"]["import_error"] = str(e)
                    validation_result["errors"]["import_error_trace"] = _tb.format_exc()
                    logger.error(f"{type_id}: Driver import failed: {e}")
            
            # Step 4: Check core version compatibility
            min_core_version = manifest_data.get("min_core_version", "0.1.0")
            # TODO: Implement actual version comparison with current core version
            # For now, assume compatibility
            
        except Exception as e:
            import traceback as _tb
            validation_result["status"] = "invalid"
            validation_result["errors"]["validation_error"] = str(e)
            validation_result["errors"]["validation_error_trace"] = _tb.format_exc()
            logger.error(f"{type_id}: Validation failed with exception: {e}")
        
        # Stage C: Update database and notify
        await self._update_integration_type_status(type_id, validation_result, manifest_data)
        
        return validation_result
    
    async def _import_and_inspect_driver(self, type_path: Path, entrypoint: str) -> tuple:
        """
        Import driver module and inspect its methods.
        
        Args:
            type_path: Path to integration folder
            entrypoint: Driver entrypoint (e.g., "driver:ProxmoxVeDriver")
            
        Returns:
            Tuple of (driver_class, method_names)
        """
        module_name, class_name = entrypoint.split(":", 1)
        module_path = type_path / f"{module_name}.py"
        
        if not module_path.exists():
            raise ImportError(f"Driver module not found: {module_path}")
        
        # Create a unique module name to avoid conflicts
        spec_name = f"walnut_integration_{type_path.name}_{module_name}"
        
        try:
            # Import the module
            spec = importlib.util.spec_from_file_location(spec_name, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load module spec from {module_path}")
            
            module = importlib.util.module_from_spec(spec)
            
            # Add to sys.modules temporarily for imports within the module
            sys.modules[spec_name] = module
            spec.loader.exec_module(module)
            
            # Get the driver class
            if not hasattr(module, class_name):
                raise ImportError(f"Class {class_name} not found in {module_path}")
            
            driver_class = getattr(module, class_name)
            
            # Inspect public methods
            method_names = [
                name for name, method in inspect.getmembers(driver_class, predicate=inspect.isfunction)
                if not name.startswith("_")
            ]
            
            return driver_class, method_names
            
        finally:
            # Clean up sys.modules
            if spec_name in sys.modules:
                del sys.modules[spec_name]
    
    async def _update_integration_type_status(
        self, 
        type_id: str, 
        validation_result: Dict[str, Any], 
        manifest_data: Dict[str, Any]
    ) -> None:
        """
        Update integration type in database with validation results.
        """
        async with get_db_session() as session:
            # Use sync database operations
            def _update_sync():
                integration_type = session.query(IntegrationType).filter(IntegrationType.id == type_id).first()
                
                if integration_type is None:
                    logger.error(f"Integration type {type_id} not found in database")
                    return None
                
                # Update fields from validation
                integration_type.status = validation_result["status"]
                integration_type.errors = validation_result["errors"] if validation_result["errors"] else None
                integration_type.last_validated_at = datetime.now(timezone.utc)
                
                # Update from manifest data if validation was successful
            if validation_result["status"] == "valid":
                integration_type.name = manifest_data.get("name", integration_type.name)
                    integration_type.version = manifest_data.get("version", integration_type.version)
                    integration_type.min_core_version = manifest_data.get("min_core_version", integration_type.min_core_version)
                    integration_type.category = manifest_data.get("category", integration_type.category)
                    integration_type.capabilities = manifest_data.get("capabilities", [])
                    integration_type.schema_connection = manifest_data.get("schema", {}).get("connection", {})
                    integration_type.defaults = manifest_data.get("defaults")
                    integration_type.test_config = manifest_data.get("test")
                    integration_type.driver_entrypoint = manifest_data.get("driver", {}).get("entrypoint", "")
                
                session.commit()
                return integration_type
            
            # Run update in thread
            integration_type = await anyio.to_thread.run_sync(_update_sync)
            
            # Notify WebSocket clients
            if self.websocket_manager and integration_type:
                await self.websocket_manager.broadcast_json({
                    "type": "integration_type.updated",
                    "data": {
                        "id": type_id,
                        "status": integration_type.status,
                        "errors": integration_type.errors,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                })
    
    async def get_integration_types(self) -> List[Dict[str, Any]]:
        """Get all integration types from database."""
        async with get_db_session() as session:
            # Use anyio to run sync database query
            def _get_types():
                types = session.query(IntegrationType).all()
                return [
                    {
                        "id": t.id,
                        "name": t.name,
                        "version": t.version,
                        "min_core_version": t.min_core_version,
                        "category": t.category,
                        "status": t.status,
                        "errors": t.errors,
                        "capabilities": t.capabilities,
                        "schema_connection": t.schema_connection,
                        "last_validated_at": t.last_validated_at.isoformat() if t.last_validated_at else None,
                        "created_at": t.created_at.isoformat(),
                        "updated_at": t.updated_at.isoformat()
                    }
                    for t in types
                ]
            
            return await anyio.to_thread.run_sync(_get_types)
    
    async def remove_integration_type(self, type_id: str) -> bool:
        """
        Remove an integration type and its folder.
        
        Args:
            type_id: Integration type ID to remove
            
        Returns:
            True if removed successfully
        """
        async with get_db_session() as session:
            def _remove_sync():
                integration_type = session.query(IntegrationType).filter(IntegrationType.id == type_id).first()
                
                if integration_type is None:
                    return None
                
                # Remove folder if it exists
                type_path = Path(integration_type.path)
                if type_path.exists():
                    import shutil
                    try:
                        shutil.rmtree(type_path)
                        logger.info(f"Removed integration folder: {type_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove folder {type_path}: {e}")
                
                # Mark type as unavailable (don't delete to preserve instance references)
                integration_type.status = "unavailable"
                session.commit()
                return integration_type
            
            # Run removal in thread
            integration_type = await anyio.to_thread.run_sync(_remove_sync)
            
            if integration_type is None:
                return False
            
            # Notify WebSocket clients
            if self.websocket_manager:
                await self.websocket_manager.broadcast_json({
                    "type": "integration_type.removed",
                    "data": {
                        "id": type_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                })
            
            return True
    
    async def validate_single_type(self, type_id: str) -> Dict[str, Any]:
        """
        Re-validate a single integration type.
        
        Args:
            type_id: Integration type ID to validate
            
        Returns:
            Validation result
        """
        async with get_db_session() as session:
            def _get_type_sync():
                integration_type = session.query(IntegrationType).filter(IntegrationType.id == type_id).first()
                return integration_type
            
            # Get integration type
            integration_type = await anyio.to_thread.run_sync(_get_type_sync)
            
            if integration_type is None:
                return {"success": False, "error": "Integration type not found"}
            
            type_path = Path(integration_type.path)
            if not type_path.exists():
                # Mark as unavailable
                def _mark_unavailable():
                    integration_type.status = "unavailable"
                    session.commit()
                
                await anyio.to_thread.run_sync(_mark_unavailable)
                return {"success": False, "error": "Integration folder not found"}
            
            # Read manifest
            plugin_yaml_path = type_path / "plugin.yaml"
            if not plugin_yaml_path.exists():
                return {"success": False, "error": "plugin.yaml not found"}
            
            with open(plugin_yaml_path, 'r') as f:
                manifest_data = yaml.safe_load(f)
            
            # Run validation
            validation_result = await self._validate_integration_type({
                "id": type_id,
                "path": str(type_path),
                "manifest_data": manifest_data
            })
            
            return {"success": True, "result": validation_result}


# Global registry instance
_registry_instance: Optional[IntegrationTypeRegistry] = None


def get_integration_registry() -> IntegrationTypeRegistry:
    """Get the global integration registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = IntegrationTypeRegistry()
    return _registry_instance


def set_integration_registry(registry: IntegrationTypeRegistry) -> None:
    """Set the global integration registry instance."""
    global _registry_instance
    _registry_instance = registry
