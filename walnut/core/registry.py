"""
Manages the lifecycle of integration types, instances, and drivers.
"""
import yaml
import importlib.util
from typing import Dict, List, Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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

    async def load_types_from_db(self, db: AsyncSession):
        """Loads all integration types from the database into the cache."""
        stmt = select(IntegrationType)
        result = await db.execute(stmt)
        types = result.scalars().all()
        self.integration_types = {t.name: t for t in types}
        print(f"Loaded {len(self.integration_types)} integration types into registry.")

    async def sync_manifests_to_db(self, db: AsyncSession, manifest_root_dir: Path):
        """Syncs all manifests from a directory into the database."""
        loader = ManifestLoader(manifest_root_dir)
        loaded_manifests = loader.load_all()

        for item in loaded_manifests:
            manifest: IntegrationManifest = item["manifest"]
            path: Path = item["path"]

            stmt = select(IntegrationType).where(IntegrationType.name == manifest.id)
            existing_type = (await db.execute(stmt)).scalars().first()

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

        await db.commit()
        await self.load_types_from_db(db)

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
