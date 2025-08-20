"""
API endpoints for managing the walNUT Integration Framework.

This module provides a comprehensive set of endpoints for discovering,
configuring, and managing integration types and their instances. It handles
everything from syncing manifest files to testing instance connectivity.
"""

from pathlib import Path
from typing import List, Dict, Any
import yaml

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session
from walnut.database import models
from walnut.core import registry as registry_manager
from walnut.core.manifests import IntegrationManifest

# --- Pydantic Schemas for API ---

class IntegrationTypeOut(BaseModel):
    """Represents an available type of integration, loaded from a manifest."""
    name: str = Field(description="The unique name of the integration type (e.g., 'proxmox').")
    version: str = Field(description="The version of the integration driver.")
    min_core_version: str = Field(description="The minimum version of walNUT required to run this integration.")
    description: str = Field(description="A human-readable description of what the integration does.")
    capabilities: List[Dict[str, Any]] = Field(description="A list of capabilities this integration provides (e.g., 'shutdown', 'monitor').")
    config_fields: List[Dict[str, Any]] = Field(description="A list of configuration fields required by this integration.")
    secret_fields: List[Dict[str, Any]] = Field(description="A list of secret fields (like passwords or API keys) required by this integration.")

    @classmethod
    def from_orm(cls, type_model: models.IntegrationType):
        """Create a response model from a database ORM instance."""
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
    """Request model for creating or updating an integration instance."""
    type_name: str = Field(description="The name of the integration type to use for this instance.")
    name: str = Field(description="A unique machine-readable name for the instance.")
    display_name: str = Field(description="A human-readable name for the instance shown in the UI.")
    config: Dict[str, Any] = Field(description="A dictionary of configuration values for the instance.")
    secrets: Dict[str, str] = Field(description="A dictionary of secret values. These are write-only and will be stored securely.")
    enabled: bool = Field(True, description="Whether the integration instance is enabled.")

class IntegrationInstanceOut(BaseModel):
    """Response model representing a configured integration instance."""
    id: int = Field(description="The unique ID of the instance.")
    name: str = Field(description="The unique machine-readable name of the instance.")
    display_name: str = Field(description="The human-readable name of the instance.")
    type_name: str = Field(description="The type of integration this instance is based on.")
    enabled: bool = Field(description="Whether the integration instance is currently enabled.")
    health_status: str = Field(description="The last known health status of the instance (e.g., 'healthy', 'unhealthy').")
    state: str = Field(description="The current state of the circuit breaker for this instance (e.g., 'closed', 'open').")
    config: Dict[str, Any] = Field(description="The non-secret configuration values for this instance.")

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, instance: models.IntegrationInstance):
        """Create a response model from a database ORM instance."""
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

@router.post(
    "/types/sync",
    status_code=200,
    summary="Sync integration types from manifests",
    responses={500: {"description": "An internal error occurred during the sync process."}},
)
async def sync_integration_types(user: User = Depends(current_active_user)):
    """
    Scans the local `integrations` directory for manifest files (`plugin.yaml`),
    and syncs them with the database. This endpoint should be called when new
    integrations are added or updated.
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

@router.get(
    "/types",
    response_model=List[IntegrationTypeOut],
    summary="List available integration types",
    responses={500: {"description": "An internal error occurred while loading types."}},
)
async def list_integration_types(user: User = Depends(current_active_user)):
    """
    Lists all available integration types that have been synced from manifests.
    This provides the necessary information for a UI to render a list of
    integrations that can be configured.
    """
    try:
        if not registry_manager.registry.integration_types:
            async with get_db_session() as db:
                registry_manager.registry.load_types_from_db(db)
        
        return [IntegrationTypeOut.from_orm(t) for t in registry_manager.registry.integration_types.values()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load integration types: {str(e)}")

@router.post(
    "/instances",
    response_model=IntegrationInstanceOut,
    status_code=201,
    summary="Create an integration instance",
    responses={
        400: {"description": "Invalid input data, such as a missing or invalid integration type."},
        500: {"description": "An unexpected internal error occurred."},
    },
)
async def create_integration_instance(
    instance_in: IntegrationInstanceIn,
    user: User = Depends(current_active_user),
):
    """
    Creates and configures a new instance of an integration type.
    The provided secrets are encrypted and stored securely.
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

@router.get(
    "/instances",
    response_model=List[IntegrationInstanceOut],
    summary="List all integration instances",
    responses={500: {"description": "An internal error occurred."}},
)
async def list_integration_instances(user: User = Depends(current_active_user)):
    """
    Lists all currently configured integration instances.
    """
    try:
        async with get_db_session() as db:
            instances = db.query(models.IntegrationInstance).all()
            return [IntegrationInstanceOut.from_orm(instance) for instance in instances]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integration instances: {str(e)}")

@router.delete(
    "/instances/{instance_id}",
    status_code=204,
    summary="Delete an integration instance",
    responses={
        404: {"description": "Integration instance not found."},
        500: {"description": "An internal error occurred."},
    },
)
async def delete_integration_instance(
    instance_id: int,
    user: User = Depends(current_active_user),
):
    """
    Deletes an integration instance and its associated secrets.
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

@router.put(
    "/instances/{instance_id}",
    response_model=IntegrationInstanceOut,
    summary="Update an integration instance",
    responses={
        400: {"description": "Invalid input data."},
        404: {"description": "Integration instance not found."},
        500: {"description": "An unexpected internal error occurred."},
    },
)
async def update_integration_instance(
    instance_id: int,
    instance_in: IntegrationInstanceIn,
    user: User = Depends(current_active_user),
):
    """
    Updates an existing integration instance.
    If new secrets are provided, they will overwrite the old ones.
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

@router.post(
    "/instances/{instance_id}/test",
    status_code=200,
    summary="Test integration instance connection",
    responses={
        404: {"description": "Integration instance not found."},
        500: {"description": "An internal error occurred during the connection test."},
    },
)
async def test_integration_instance(
    instance_id: int,
    user: User = Depends(current_active_user),
):
    """
    Tests the connection for a given integration instance to ensure it is
    configured correctly and can communicate with the target system.
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