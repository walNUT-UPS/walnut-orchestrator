"""
API endpoints for managing the walNUT Integration Framework.

This includes endpoints for managing integration types, instances,
secrets, targets, and health monitoring.
"""

from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from walnut.database.connection import get_db_session
from walnut.database import models
from walnut.core import registry as registry_manager
from walnut.core.manifests import IntegrationManifest

# --- Pydantic Schemas for API ---

class IntegrationTypeOut(BaseModel):
    name: str
    version: str
    min_core_version: str
    description: str
    capabilities: List[Dict[str, Any]]
    config_fields: List[Dict[str, Any]]
    secret_fields: List[Dict[str, Any]]

    @classmethod
    def from_orm(cls, type_model: models.IntegrationType):
        manifest_data = yaml.safe_load(type_model.manifest_yaml)
        manifest = IntegrationManifest.parse_obj(manifest_data)
        return cls(
            name=type_model.name,
            version=type_model.version,
            min_core_version=manifest.min_core_version,
            description=manifest.description,
            capabilities=[cap.dict() for cap in manifest.capabilities],
            config_fields=[field.dict() for field in manifest.config_fields],
            secret_fields=[field.dict() for field in manifest.secret_fields],
        )

class IntegrationInstanceIn(BaseModel):
    type_name: str
    name: str
    display_name: str
    config: Dict[str, Any]
    secrets: Dict[str, str] = Field(..., description="Secrets will not be stored in plain text.")
    enabled: bool = True

class IntegrationInstanceOut(BaseModel):
    id: int
    name: str
    display_name: str
    type_name: str
    enabled: bool
    health_status: str
    state: str # Circuit breaker state
    config: Dict[str, Any]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, instance: models.IntegrationInstance):
        return cls(
            id=instance.id,
            name=instance.name,
            display_name=instance.display_name,
            type_name=instance.type.name, # Assumes 'type' relationship is loaded
            enabled=instance.enabled,
            health_status=instance.health_status,
            state=instance.state,
            config=instance.config
        )


# --- API Router ---

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["Integrations"],
)

@router.post("/types/sync", status_code=200)
async def sync_integration_types(db: AsyncSession = Depends(get_db_session)):
    """
    Scans the manifests directory and syncs integration types with the database.
    """
    manifest_dir = Path("./integrations/manifests")
    await registry_manager.registry.sync_manifests_to_db(db, manifest_dir)
    # Also reload the types into the registry cache
    await registry_manager.registry.load_types_from_db(db)
    return {"status": "success", "message": "Integration types synced from manifests."}

@router.get("/types", response_model=List[IntegrationTypeOut])
async def list_integration_types(db: AsyncSession = Depends(get_db_session)):
    """
    Lists all available integration types.
    """
    if not registry_manager.registry.integration_types:
        await registry_manager.registry.load_types_from_db(db)

    return [IntegrationTypeOut.from_orm(t) for t in registry_manager.registry.integration_types.values()]

@router.post("/instances", response_model=IntegrationInstanceOut, status_code=201)
async def create_integration_instance(
    instance_in: IntegrationInstanceIn,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Creates a new integration instance.
    """
    try:
        instance = await registry_manager.registry.create_instance(
            db=db,
            type_name=instance_in.type_name,
            instance_name=instance_in.name,
            display_name=instance_in.display_name,
            config=instance_in.config,
            instance_secrets=instance_in.secrets,
            enabled=instance_in.enabled,
        )

        # We need to load the type relationship to get the type_name
        await db.refresh(instance, attribute_names=["type"])

        return IntegrationInstanceOut.from_orm(instance)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
