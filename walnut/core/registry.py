"""
Manages the lifecycle of integration types, instances, and drivers.
"""
import yaml
import importlib.util
from typing import Dict, List, Optional, Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from pathlib import Path

from walnut.database.models import IntegrationType, IntegrationInstance, Target
from walnut.core.manifests import IntegrationManifest, ManifestLoader
from walnut.core import secrets

# A placeholder for the driver's base class, which individual drivers don't need to import
class BaseDriver:
    def __init__(self, instance: IntegrationInstance, secrets: Dict[str, str]):
        pass

class IntegrationRegistry:
    """A registry for managing integration types and instances."""

    def __init__(self):
        self.integration_types: Dict[str, IntegrationType] = {}

    def load_types_from_db(self, db: Session):
        """Loads all integration types from the database into the cache."""
        types = db.query(IntegrationType).all()
        self.integration_types = {t.name: t for t in types}
        print(f"Loaded {len(self.integration_types)} integration types into registry.")

    def sync_manifests_to_db(self, db: Session, manifest_root_dir: Path):
        """Syncs all manifests from a directory into the database."""
        loader = ManifestLoader(manifest_root_dir)
        loaded_manifests = loader.load_all()

        for item in loaded_manifests:
            manifest: IntegrationManifest = item["manifest"]
            path: Path = item["path"]

            existing_type = db.query(IntegrationType).filter(IntegrationType.name == manifest.id).first()

            driver_entrypoint = manifest.driver.entrypoint
            driver_path = str(path.joinpath(driver_entrypoint.split(':')[0] + '.py'))

            if existing_type:
                if (existing_type.version != manifest.version or
                    existing_type.driver_path != driver_path):
                    existing_type.version = manifest.version
                    existing_type.manifest_yaml = yaml.dump(manifest.dict())
                    existing_type.capabilities = [cap.dict() for cap in manifest.capabilities]
                    existing_type.driver_path = driver_path
                    existing_type.driver_entrypoint = driver_entrypoint
                    print(f"Updated integration type: {manifest.id} v{manifest.version}")
            else:
                new_type = IntegrationType(
                    name=manifest.id,
                    version=manifest.version,
                    min_core_version=manifest.min_core_version,
                    manifest_yaml=yaml.dump(manifest.dict()),
                    capabilities=[cap.dict() for cap in manifest.capabilities],
                    driver_path=driver_path,
                    driver_entrypoint=driver_entrypoint,
                )
                db.add(new_type)
                print(f"Registered new integration type: {manifest.id} v{manifest.version}")

        # Commit is handled by the context manager
        self.load_types_from_db(db)

    def create_instance(self, db: Session, type_name: str, instance_name: str, 
                       display_name: str, config: Dict[str, Any], 
                       instance_secrets: Dict[str, str], enabled: bool = True) -> IntegrationInstance:
        """Creates a new integration instance."""
        # Get the integration type
        integration_type = db.query(IntegrationType).filter(IntegrationType.name == type_name).first()
        if not integration_type:
            raise ValueError(f"Integration type '{type_name}' not found")
        
        # Create the instance
        instance = IntegrationInstance(
            name=instance_name,
            display_name=display_name,
            type_id=integration_type.id,
            enabled=enabled,
            config=config,
            health_status="unknown",
            state="open"
        )
        
        db.add(instance)
        db.flush()  # Get the ID
        
        # Store secrets if provided
        if instance_secrets:
            for key, value in instance_secrets.items():
                secrets.store_secret(db, f"integration.{instance.id}.{key}", value)
        
        return instance

    def update_instance_secrets(self, db: Session, instance: IntegrationInstance, 
                              new_secrets: Dict[str, str]):
        """Updates secrets for an integration instance."""
        for key, value in new_secrets.items():
            secrets.store_secret(db, f"integration.{instance.id}.{key}", value)

    def test_instance_connection(self, db: Session, instance: IntegrationInstance) -> bool:
        """Tests the connection for an integration instance."""
        try:
            # For now, return a simple success - in real implementation this would
            # load the driver and test the actual connection
            return True
        except Exception as e:
            print(f"Connection test failed for {instance.display_name}: {e}")
            return False

def get_driver(instance: IntegrationInstance, secrets_dict: Dict[str, str]) -> Any:
    """
    Factory function to get a driver instance for a given integration.
    """
    driver_path_str = instance.type.driver_path
    entrypoint = instance.type.driver_entrypoint

    module_name, class_name = entrypoint.split(':')

    spec = importlib.util.spec_from_file_location(module_name, driver_path_str)
    if not spec or not spec.loader:
        raise ImportError(f"Could not create module spec for driver at {driver_path_str}")

    driver_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver_module)

    driver_class = getattr(driver_module, class_name)

    return driver_class(instance, secrets_dict)

# Global registry instance
registry = IntegrationRegistry()
