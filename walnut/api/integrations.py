"""
API endpoints for managing the walNUT Integration Framework.

This includes endpoints for managing integration types, instances,
secrets, targets, and health monitoring.
"""

from pathlib import Path
from typing import List, Dict, Any
import yaml

from fastapi import APIRouter, HTTPException
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
    prefix="/v1/integrations",
    tags=["Integrations"],
)

@router.post("/types/sync", status_code=200)
async def sync_integration_types():
    """
    Scans the manifests directory and syncs integration types with the database.
    """
    try:
        async with get_db_session() as db:
            manifest_dir = Path("./integrations")
            registry_manager.registry.sync_manifests_to_db(db, manifest_dir)
            # Also reload the types into the registry cache
            registry_manager.registry.load_types_from_db(db)
        return {"status": "success", "message": "Integration types synced from manifests."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync integration types: {str(e)}")

@router.get("/types", response_model=List[IntegrationTypeOut])
async def list_integration_types():
    """
    Lists all available integration types.
    """
    try:
        if not registry_manager.registry.integration_types:
            async with get_db_session() as db:
                registry_manager.registry.load_types_from_db(db)
        
        return [IntegrationTypeOut.from_orm(t) for t in registry_manager.registry.integration_types.values()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load integration types: {str(e)}")

@router.post("/instances", response_model=IntegrationInstanceOut, status_code=201)
async def create_integration_instance(
    instance_in: IntegrationInstanceIn
):
    """
    Creates a new integration instance.
    """
    try:
        async with get_db_session() as db:
            instance = registry_manager.registry.create_instance(
                db=db,
                type_name=instance_in.type_name,
                instance_name=instance_in.name,
                display_name=instance_in.display_name,
                config=instance_in.config,
                instance_secrets=instance_in.secrets,
                enabled=instance_in.enabled,
            )

            # We need to load the type relationship to get the type_name
            db.refresh(instance)

            return IntegrationInstanceOut.from_orm(instance)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/instances", response_model=List[IntegrationInstanceOut])
async def list_integration_instances():
    """
    Lists all integration instances.
    """
    try:
        async with get_db_session() as db:
            instances = db.query(models.IntegrationInstance).all()
            return [IntegrationInstanceOut.from_orm(instance) for instance in instances]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integration instances: {str(e)}")

@router.delete("/instances/{instance_id}", status_code=204)
async def delete_integration_instance(
    instance_id: int
):
    """
    Deletes an integration instance.
    """
    try:
        async with get_db_session() as db:
            instance = db.query(models.IntegrationInstance).filter(
                models.IntegrationInstance.id == instance_id
            ).first()
            
            if not instance:
                raise HTTPException(status_code=404, detail="Integration instance not found")
            
            db.delete(instance)
            # Commit is handled by the context manager
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete integration instance: {str(e)}")

@router.put("/instances/{instance_id}", response_model=IntegrationInstanceOut)
async def update_integration_instance(
    instance_id: int,
    instance_in: IntegrationInstanceIn
):
    """
    Updates an integration instance.
    """
    try:
        async with get_db_session() as db:
            instance = db.query(models.IntegrationInstance).filter(
                models.IntegrationInstance.id == instance_id
            ).first()
            
            if not instance:
                raise HTTPException(status_code=404, detail="Integration instance not found")
            
            instance.name = instance_in.name
            instance.display_name = instance_in.display_name
            instance.config = instance_in.config
            instance.enabled = instance_in.enabled
            
            # Update secrets if provided
            if instance_in.secrets:
                registry_manager.registry.update_instance_secrets(
                    db, instance, instance_in.secrets
                )
            
            db.refresh(instance)
            return IntegrationInstanceOut.from_orm(instance)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/instances/{instance_id}/test", status_code=200)
async def test_integration_instance(
    instance_id: int
):
    """
    Tests the connection for an integration instance.
    """
    try:
        async with get_db_session() as db:
            instance = db.query(models.IntegrationInstance).filter(
                models.IntegrationInstance.id == instance_id
            ).first()
            
            if not instance:
                raise HTTPException(status_code=404, detail="Integration instance not found")
            
            # Test the connection using the registry
            success = registry_manager.registry.test_instance_connection(
                db, instance
            )
            
            if success:
                return {
                    "status": "success", 
                    "message": f"Successfully connected to {instance.display_name}"
                }
            else:
                return {
                    "status": "error", 
                    "message": f"Failed to connect to {instance.display_name}: Connection test failed"
                }
        
    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Failed to test connection: {str(e)}"
        }