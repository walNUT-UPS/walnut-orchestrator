"""
API endpoints for the walNUT Integration Framework (New Architecture).

This implements the new integrations architecture with:
- Types: Validated plugins from ./integrations/<slug>/
- Instances: Configured connections created from types
- File upload support for .int packages
- WebSocket notifications for real-time updates
"""

import asyncio
import anyio
import os
import sys
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, join
from sqlalchemy.ext.asyncio import AsyncSession

from walnut.auth.deps import current_active_user, require_current_user
from walnut.database.connection import get_db_session, get_db_session_dependency
from walnut.database.models import IntegrationType, IntegrationInstance, IntegrationSecret
from walnut.core.integration_registry import get_integration_registry
from walnut.core.websocket_manager import get_websocket_manager  # noqa: F401  (kept for future WS broadcasts)
from walnut.core.websocket_manager import websocket_manager
import uuid


# --- Pydantic Schemas ---

class IntegrationTypeOut(BaseModel):
    """Integration type response schema."""
    id: str
    name: str
    version: str
    min_core_version: str
    category: str
    status: str
    errors: Optional[Dict[str, Any]]
    capabilities: List[Dict[str, Any]]
    schema_connection: Dict[str, Any]
    last_validated_at: Optional[str]
    created_at: str
    updated_at: str


class IntegrationInstanceIn(BaseModel):
    """Integration instance creation request."""
    type_id: str = Field(..., description="Integration type ID")
    name: str = Field(..., description="Unique instance name")
    config: Dict[str, Any] = Field(..., description="Non-secret configuration values")
    secrets: Dict[str, str] = Field(default_factory=dict, description="Secret field values")


class IntegrationInstanceOut(BaseModel):
    """Integration instance response schema."""
    instance_id: int
    type_id: str
    name: str
    config: Dict[str, Any]
    state: str
    last_test: Optional[str]
    latency_ms: Optional[int]
    flags: Optional[List[str]]
    created_at: str
    updated_at: str

    # Type information
    type_name: Optional[str] = None
    type_category: Optional[str] = None


class InstanceTestResult(BaseModel):
    """Instance connection test result."""
    success: bool
    status: str
    latency_ms: Optional[int] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class DiscoveryResult(BaseModel):
    """Integration type discovery result."""
    discovered: int
    valid: int
    invalid: int
    errors: int
    completed_at: str


# --- API Router ---

router = APIRouter(
    prefix="/integrations",
    tags=["Integrations"],
)


# --- Integration Types Endpoints ---

@router.get("/types", response_model=List[IntegrationTypeOut])
async def list_integration_types(
    rescan: bool = Query(False, description="Force rescan of integration types"),
    current_user=Depends(require_current_user)
):
    """
    List all integration types. Optionally trigger discovery and validation.

    The rescan parameter triggers the complete discovery and validation pipeline:
    - Stage A: Scan ./integrations/ folders
    - Stage B: Validate manifests and drivers
    - Stage C: Update database with results

    WebSocket events are broadcast during the process for real-time UI updates.
    """
    try:
        registry = get_integration_registry()

        if rescan:
            # Trigger async discovery and validation
            asyncio.create_task(registry.discover_and_validate_all(force_rescan=True))

        # Return current state
        types = await registry.get_integration_types()
        return [IntegrationTypeOut(**type_data) for type_data in types]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integration types: {str(e)}")


@router.post("/types/upload")
async def upload_integration_package(
    file: UploadFile = File(..., description="Integration package (.int file)"),
    current_user=Depends(require_current_user),
    db: AsyncSession = Depends(get_db_session_dependency)
):
    """
    Upload and install an integration package (.int file).

    Process:
    1. Validate .int file (ZIP with .int extension)
    2. Safe unzip to staging area (prevent zip-slip attacks)
    3. Validate manifest and driver in staging
    4. Atomic move to ./integrations/<slug>/
    5. Run validation pipeline and update database
    """
    try:
        logs: List[Dict[str, Any]] = []
        def add_log(message: str, level: str = "info", step: Optional[str] = None):
            logs.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
                "step": step,
            })

        add_log("Starting upload request", step="start")
        if not file.filename or not file.filename.endswith(".int"):
            add_log("Invalid file extension; expected .int", level="error", step="validate")
            raise HTTPException(status_code=400, detail={"error": "File must have .int extension", "logs": logs})

        # File size limit (10MB) — compute after reading
        max_size = 10 * 1024 * 1024  # 10MB

        registry = get_integration_registry()
        integrations_path = Path("./integrations").resolve()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            staging_path = temp_path / "staging"

            # Save uploaded file to a temp path
            upload_path = temp_path / file.filename
            content = await file.read()
            if len(content) > max_size:
                add_log("File too large (>10MB)", level="error", step="read")
                raise HTTPException(status_code=413, detail={"error": "File too large (max 10MB)", "logs": logs})

            upload_path.write_bytes(content)
            add_log(f"Received file: {file.filename} ({len(content)} bytes)", step="read")

            # Validate ZIP
            if not zipfile.is_zipfile(upload_path):
                add_log("Uploaded file is not a valid ZIP", level="error", step="zip-validate")
                raise HTTPException(status_code=400, detail={"error": "Invalid ZIP file", "logs": logs})

            try:
                with zipfile.ZipFile(upload_path, "r") as zip_ref:
                    # Check for zip-slip attacks
                    for member in zip_ref.namelist():
                        normalized = os.path.normpath(member)
                        if normalized.startswith("..") or os.path.isabs(member):
                            add_log(f"Unsafe path in archive: {member}", level="error", step="zip-validate")
                            raise HTTPException(status_code=400, detail={"error": "Unsafe file path in archive", "logs": logs})

                    # Extract to staging
                    zip_ref.extractall(staging_path)
                    add_log("Extracted archive to staging", step="extract")

                # Find plugin.yaml in extracted contents
                plugin_yaml_candidates = list(staging_path.rglob("plugin.yaml"))
                if not plugin_yaml_candidates:
                    add_log("No plugin.yaml found in package", level="error", step="manifest")
                    raise HTTPException(status_code=400, detail={"error": "No plugin.yaml found in package", "logs": logs})

                plugin_yaml_path = plugin_yaml_candidates[0]
                integration_folder = plugin_yaml_path.parent

                # Validate plugin.yaml
                with open(plugin_yaml_path, "r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f)

                if not manifest_data or not isinstance(manifest_data, dict):
                    add_log("Invalid plugin.yaml content", level="error", step="manifest-validate")
                    raise HTTPException(status_code=400, detail={"error": "Invalid plugin.yaml content", "logs": logs})

                type_id = manifest_data.get("id")
                if not type_id:
                    add_log("Missing 'id' field in plugin.yaml", level="error", step="manifest-validate")
                    raise HTTPException(status_code=400, detail={"error": "Missing 'id' field in plugin.yaml", "logs": logs})

                add_log(f"Found manifest with id '{type_id}'", step="manifest-validate")

                # Check if type already exists
                result = db.execute(select(IntegrationType).where(IntegrationType.id == type_id))
                existing_type = result.scalar_one_or_none()
                if existing_type:
                    add_log(f"Integration type '{type_id}' already exists", level="error", step="pre-install")
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": f"Integration type '{type_id}' already exists. Remove it first to upload a new version.",
                            "logs": logs,
                        }
                    )

                # Atomic move to integrations folder
                target_path = integrations_path / type_id
                if target_path.exists():
                    shutil.rmtree(target_path)

                shutil.move(str(integration_folder), str(target_path))
                add_log(f"Installed integration files to {target_path}", step="install")

                # Ensure type record exists for this new upload (no global rescan)
                await get_integration_registry().ensure_type_record(type_id, target_path, manifest_data)

                # Trigger validation for the new type only
                add_log("Starting validation pipeline", step="validate")
                validation_result = await registry.validate_single_type(type_id)
                add_log("Validation pipeline finished", step="validate")

                return {
                    "success": True,
                    "type_id": type_id,
                    "message": (
                        "Integration package uploaded and validated"
                        if validation_result.get("success")
                        else "Integration package uploaded but registered with errors"
                    ),
                    "validation": validation_result,
                    "logs": logs,
                }

            except HTTPException:
                raise
            except Exception as e:
                import traceback
                traceback_str = traceback.format_exc()
                add_log(f"Unexpected error during upload: {e}", level="error", step="error")
                raise HTTPException(status_code=500, detail={"error": f"Upload failed: {e}", "trace": traceback_str, "logs": logs})

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        # Outer catch-all
        return {
            "success": False,
            "message": f"Upload failed: {e}",
            "error": str(e),
            "trace": traceback_str,
            "logs": [{
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": "error",
                "message": f"Upload failed: {e}",
                "step": "error"
            }]
        }


# Accept trailing slash as well to avoid 405 from clients that append '/'
@router.post("/types/upload/")
async def upload_integration_package_slash(
    file: UploadFile = File(..., description="Integration package (.int file)"),
    current_user=Depends(require_current_user),
    db: AsyncSession = Depends(get_db_session_dependency)
):
    return await upload_integration_package(file=file, current_user=current_user, db=db)


import logging

upload_logger = logging.getLogger("walnut.upload")
upload_logger.setLevel(logging.INFO)

# Add console handler for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
upload_logger.addHandler(console_handler)

async def _broadcast_upload_log(job_id: str, level: str, message: str, step: Optional[str] = None):
    try:
        if websocket_manager:
            upload_logger.info(f"[UPLOAD DEBUG] Broadcasting: {level} - {message} (step: {step}) for job {job_id}")
            upload_logger.info(f"[UPLOAD DEBUG] Authenticated clients: {websocket_manager.get_authenticated_count()}")
            await websocket_manager.broadcast_json({
                "type": "integration_upload.log",
                "data": {
                    "job_id": job_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": level,
                    "message": message,
                    "step": step,
                },
            })
            upload_logger.info(f"[UPLOAD DEBUG] Broadcast completed")
        else:
            upload_logger.error(f"[UPLOAD DEBUG] No websocket_manager available")
    except Exception as e:
        upload_logger.error(f"[UPLOAD DEBUG] Broadcast error: {e}")
        pass


@router.post("/types/upload/stream")
async def upload_integration_package_stream(
    file: UploadFile = File(..., description="Integration package (.int file)"),
    current_user=Depends(require_current_user),
):
    """
    Starts an asynchronous upload + validation job and streams logs via WebSocket.

    Returns a job_id immediately. Clients should listen on the WS for
    messages of type 'integration_upload.*' with matching job_id.
    """
    job_id = str(uuid.uuid4())

    # IMPORTANT: Read the uploaded file before starting the background task.
    # FastAPI closes the UploadFile as soon as the request returns, so any
    # background task must not reference `file` directly.
    orig_filename = file.filename or f"upload_{job_id}.int"
    if not orig_filename.endswith(".int"):
        # Validate extension up front since we won't touch `file` later
        raise HTTPException(status_code=400, detail="File must have .int extension")

    max_size = 10 * 1024 * 1024  # 10MB
    try:
        content = await file.read()
    except Exception as _e:
        # If the file-like object was closed prematurely, surface a clear error
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {_e}")

    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    async def _job_event(phase: str, level: str, message: str, meta: Optional[Dict[str, Any]] = None):
        try:
            await websocket_manager.send_job_event(job_id, {
                "type": "integration_job.event",
                "data": {
                    "job_id": job_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "phase": phase,
                    "level": level,
                    "message": message,
                    "meta": meta or {},
                }
            })
        except Exception:
            pass

    async def run_job():
        upload_logger.info(f"[UPLOAD DEBUG] run_job STARTED for job {job_id}")
        # Allow a brief window for the client to connect to the job stream
        try:
            await asyncio.sleep(0.4)
        except Exception:
            pass
        try:
            await _job_event("upload", "info", "Starting upload request")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                staging_path = temp_path / "staging"
                upload_path = temp_path / orig_filename
                upload_path.write_bytes(content)
                await _job_event("upload", "info", f"Received {orig_filename}", {"bytes": len(content)})

                if not zipfile.is_zipfile(upload_path):
                    await _job_event("unpack", "error", "Invalid ZIP file")
                    raise HTTPException(status_code=400, detail="Invalid ZIP file")

                with zipfile.ZipFile(upload_path, "r") as zip_ref:
                    for member in zip_ref.namelist():
                        normalized = os.path.normpath(member)
                        if normalized.startswith("..") or os.path.isabs(member):
                            await _job_event("unpack", "error", f"Unsafe path in archive: {member}")
                            raise HTTPException(status_code=400, detail="Unsafe file path in archive")
                    zip_ref.extractall(staging_path)
                await _job_event("unpack", "info", "Extracted archive to staging")

                plugin_yaml_candidates = list(staging_path.rglob("plugin.yaml"))
                if not plugin_yaml_candidates:
                    await _job_event("manifest", "error", "No plugin.yaml found in package")
                    raise HTTPException(status_code=400, detail="No plugin.yaml found in package")

                plugin_yaml_path = plugin_yaml_candidates[0]
                integration_folder = plugin_yaml_path.parent

                with open(plugin_yaml_path, "r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f)
                if not manifest_data or not isinstance(manifest_data, dict):
                    await _job_event("manifest", "error", "Invalid plugin.yaml content")
                    raise HTTPException(status_code=400, detail="Invalid plugin.yaml content")

                type_id = manifest_data.get("id")
                if not type_id:
                    await _job_event("manifest", "error", "Missing 'id' in plugin.yaml")
                    raise HTTPException(status_code=400, detail="Missing 'id' field in plugin.yaml")
                await _job_event("manifest", "info", f"Found manifest id '{type_id}'", {"type_id": type_id})

                # Ensure no conflict
                async with get_db_session() as session:
                    def _check_exists():
                        from sqlalchemy import select as _select
                        return session.execute(_select(IntegrationType).where(IntegrationType.id == type_id)).scalar_one_or_none()
                    existing = await anyio.to_thread.run_sync(_check_exists)
                    if existing:
                        await _job_event("registry", "error", f"Integration type '{type_id}' already exists")
                        raise HTTPException(status_code=409, detail=f"Integration type '{type_id}' already exists")

                # Move into ./integrations/<type_id>
                target_path = Path("./integrations").resolve() / type_id
                if target_path.exists():
                    shutil.rmtree(target_path)
                shutil.move(str(integration_folder), str(target_path))
                await _job_event("install", "info", f"Installed files to {target_path}", {"path": str(target_path)})

                # Register type record without rescanning others
                try:
                    await get_integration_registry().ensure_type_record(type_id, target_path, manifest_data)
                except Exception as _e:
                    await _job_event("registry", "error", f"Failed to register type: {_e}")
                    raise

                # Validate only this type
                await _job_event("registry", "info", "Starting validation and registry update")
                registry = get_integration_registry()
                validation_result = await registry.validate_single_type(type_id)
                # Try to extract status if shaped
                status_val = None
                try:
                    status_val = validation_result.get("result", {}).get("status") if isinstance(validation_result, dict) else None
                except Exception:
                    status_val = None
                await _job_event("registry", "info", "Validation pipeline finished", {"status": status_val})

                # Done (job-scoped)
                await websocket_manager.send_job_event(job_id, {
                    "type": "integration_job.done",
                    "data": {
                        "job_id": job_id,
                        "success": True,
                        "type_id": type_id,
                        "installed_path": str(target_path),
                        "result": validation_result,
                    },
                })

        except HTTPException as he:
            await _job_event("final", "error", f"HTTP error: {he.detail}")
            await websocket_manager.send_job_event(job_id, {
                "type": "integration_job.done",
                "data": {
                    "job_id": job_id,
                    "success": False,
                    "error": str(he.detail),
                    "errors": he.detail,
                },
            })
        except Exception as e:
            import traceback as _tb
            tb_str = _tb.format_exc()
            await _job_event("final", "error", f"Unexpected error: {e}", {"exception": str(e)})
            await websocket_manager.send_job_event(job_id, {
                "type": "integration_job.done",
                "data": {
                    "job_id": job_id,
                    "success": False,
                    "error": str(e),
                    "errors": str(e),
                    "trace": tb_str,
                },
            })

    # Spawn background job
    upload_logger.info(f"[UPLOAD DEBUG] Starting background job for {job_id}")
    task = asyncio.create_task(run_job())
    upload_logger.info(f"[UPLOAD DEBUG] Background job started for {job_id}, task: {task}")
    return {"job_id": job_id}


@router.delete("/types/{type_id}")
async def remove_integration_type(
    type_id: str,
    current_user=Depends(current_active_user)
):
    """
    Remove an integration type and its folder.

    This marks the type as 'unavailable' and removes the filesystem folder.
    Existing instances are marked with 'type_unavailable' flag.
    """
    try:
        registry = get_integration_registry()
        success = await registry.remove_integration_type(type_id)

        if not success:
            raise HTTPException(status_code=404, detail="Integration type not found")

        return {"success": True, "message": f"Integration type '{type_id}' removed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove integration type: {str(e)}")


@router.get("/types/{type_id}/manifest")
async def get_integration_manifest(
    type_id: str,
    current_user=Depends(require_current_user),
):
    """
    Return the raw plugin.yaml manifest for a given integration type.

    Reads the manifest from the filesystem using the stored IntegrationType.path
    and returns it as a YAML string so the UI can render it in a dialog.
    """
    try:
        async with get_db_session() as session:
            # Session is synchronous; run execute in a worker thread
            result = await anyio.to_thread.run_sync(
                session.execute, select(IntegrationType).where(IntegrationType.id == type_id)
            )
            integration_type = result.scalar_one_or_none()
            if not integration_type:
                raise HTTPException(status_code=404, detail="Integration type not found")

            # Prefer saved absolute path; fall back to ./integrations/<id>/plugin.yaml
            plugin_path = Path(integration_type.path) / "plugin.yaml"
            if not plugin_path.exists():
                fallback = Path("./integrations") / type_id / "plugin.yaml"
                if fallback.exists():
                    plugin_path = fallback
                else:
                    raise HTTPException(status_code=404, detail="plugin.yaml not found for this integration type")

            content = plugin_path.read_text(encoding="utf-8")
            return {"type_id": type_id, "path": str(plugin_path), "manifest_yaml": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read manifest: {str(e)}")


@router.post("/types/{type_id}/validate")
async def revalidate_integration_type(
    type_id: str,
    current_user=Depends(require_current_user)
):
    """
    Re-run validation for a specific integration type.
    """
    try:
        registry = get_integration_registry()
        result = await registry.validate_single_type(type_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Validation failed"))

        return {
            "success": True,
            "message": f"Integration type '{type_id}' revalidated",
            "result": result.get("result"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


# --- Integration Instances Endpoints ---

@router.get("/instances", response_model=List[IntegrationInstanceOut])
async def list_integration_instances(
    current_user=Depends(require_current_user)
):
    """
    List all integration instances with their current state and type information.
    """
    try:
        async with get_db_session() as session:
            stmt = (
                select(IntegrationInstance, IntegrationType)
                .join(IntegrationType, IntegrationInstance.type_id == IntegrationType.id)
            )
            # Run sync execute() in a worker thread
            result = await anyio.to_thread.run_sync(session.execute, stmt)
            rows = result.all()

            out: List[IntegrationInstanceOut] = []
            for instance, type_info in rows:
                out.append(
                    IntegrationInstanceOut(
                        instance_id=instance.instance_id,
                        type_id=instance.type_id,
                        name=instance.name,
                        config=instance.config,
                        state=instance.state,
                        last_test=instance.last_test.isoformat() if instance.last_test else None,
                        latency_ms=instance.latency_ms,
                        flags=instance.flags,
                        created_at=instance.created_at.isoformat(),
                        updated_at=instance.updated_at.isoformat(),
                        type_name=type_info.name,
                        type_category=type_info.category,
                    )
                )
            return out

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integration instances: {str(e)}")


@router.post("/instances", response_model=IntegrationInstanceOut, status_code=201)
async def create_integration_instance(
    instance_data: IntegrationInstanceIn,
    current_user=Depends(require_current_user),
    session=Depends(get_db_session_dependency)
):
    """
    Create a new integration instance from a validated integration type.

    This endpoint is called from the Hosts tab when creating a new host
    with an integration type selected. The form is generated from the
    type's schema.connection JSON Schema.
    """
    try:
        # Verify type exists and is valid
        res_type = await anyio.to_thread.run_sync(
            session.execute,
            select(IntegrationType).where(IntegrationType.id == instance_data.type_id),
        )
        integration_type = await anyio.to_thread.run_sync(res_type.scalar_one_or_none)
        if not integration_type:
            raise HTTPException(status_code=404, detail="Integration type not found")

        if integration_type.status not in ["valid", "checking"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot create instance: integration type status is '{integration_type.status}'",
            )

        # Check unique instance name
        res_existing = await anyio.to_thread.run_sync(
            session.execute,
            select(IntegrationInstance).where(IntegrationInstance.name == instance_data.name),
        )
        existing_instance = await anyio.to_thread.run_sync(res_existing.scalar_one_or_none)
        if existing_instance is not None:
            raise HTTPException(status_code=409, detail="Instance name already exists")

        # Create instance
        instance = IntegrationInstance(
            type_id=instance_data.type_id,
            name=instance_data.name,
            config=instance_data.config,
            state="unknown",
        )
        session.add(instance)
        await anyio.to_thread.run_sync(session.flush)  # get instance_id

        # Store secrets (NOTE: placeholder "encryption")
        for field_name, secret_value in instance_data.secrets.items():
            secret = IntegrationSecret(
                instance_id=instance.instance_id,
                field_name=field_name,
                secret_type="string",
                encrypted_value=secret_value.encode("utf-8"),
            )
            session.add(secret)

        # Set basic state (no active connection test here)
        instance.state = "configured"
        instance.last_test = datetime.now(timezone.utc)

        # Ensure changes are flushed so created_at/updated_at reflect values when returned
        await anyio.to_thread.run_sync(session.flush)

        return IntegrationInstanceOut(
            instance_id=instance.instance_id,
            type_id=instance.type_id,
            name=instance.name,
            config=instance.config,
            state=instance.state,
            last_test=instance.last_test.isoformat() if instance.last_test else None,
            latency_ms=instance.latency_ms,
            flags=instance.flags,
            created_at=instance.created_at.isoformat(),
            updated_at=instance.updated_at.isoformat(),
            type_name=integration_type.name,
            type_category=integration_type.category,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create integration instance: {str(e)}")


@router.post("/instances/{instance_id}/test", response_model=InstanceTestResult)
async def test_integration_instance(
    instance_id: int,
    current_user=Depends(current_active_user)
):
    """
    Test connection for an integration instance using its driver's test_connection method.
    """
    try:
        async with get_db_session() as session:
            result = await test_instance_connection(instance_id, session)

            # Update instance state and test timestamp
            query = select(IntegrationInstance).where(IntegrationInstance.instance_id == instance_id)
            db_result = session.execute(query)
            instance = db_result.scalar_one_or_none()

            if instance:
                instance.state = result.status
                instance.latency_ms = result.latency_ms
                instance.last_test = datetime.now(timezone.utc)
                await anyio.to_thread.run_sync(session.commit)

            return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.delete("/instances/{instance_id}")
async def delete_integration_instance(
    instance_id: int,
    current_user=Depends(current_active_user)
):
    """
    Delete an integration instance and its associated secrets.
    """
    try:
        async with get_db_session() as session:
            result = await anyio.to_thread.run_sync(
                session.execute,
                select(IntegrationInstance).where(IntegrationInstance.instance_id == instance_id),
            )
            instance = result.scalar_one_or_none()

            if not instance:
                raise HTTPException(status_code=404, detail="Integration instance not found")

            await anyio.to_thread.run_sync(session.delete, instance)
            await anyio.to_thread.run_sync(session.commit)

            return {"success": True, "message": f"Integration instance '{instance.name}' deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete integration instance: {str(e)}")


# --- Helper Functions ---

async def test_instance_connection(
    instance_id: int,
    session: Optional[AsyncSession] = None
) -> InstanceTestResult:
    """
    Test connection for an integration instance by loading and calling its driver.
    """
    if session is None:
        async with get_db_session() as session_ctx:
            return await test_instance_connection(instance_id, session_ctx)

    # Get instance with type information
    stmt = (
        select(IntegrationInstance, IntegrationType)
        .join(IntegrationType, IntegrationInstance.type_id == IntegrationType.id)
        .where(IntegrationInstance.instance_id == instance_id)
    )
    result = session.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Integration instance not found")

    instance, integration_type = row

    if integration_type.status not in ("valid", "checking"):
        return InstanceTestResult(
            success=False,
            status="error",
            message=f"Integration type is not ready (status: {integration_type.status})",
        )

    module_name = f"driver_{instance_id}"
    try:
        # Load driver dynamically
        type_path = Path(integration_type.path)
        driver_module, driver_class_name = integration_type.driver_entrypoint.split(":", 1)

        # Build module path (module like "driver" -> driver.py next to manifest)
        module_path = type_path / f"{driver_module}.py"
        if not module_path.exists():
            raise RuntimeError(f"Driver module not found at: {module_path}")

        import importlib.util

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load driver module: {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        driver_class = getattr(module, driver_class_name, None)
        if driver_class is None:
            raise RuntimeError(f"Driver class '{driver_class_name}' not found in module '{driver_module}'")

        # Get secrets
        secrets_query = select(IntegrationSecret).where(IntegrationSecret.instance_id == instance_id)
        secrets_result = session.execute(secrets_query)
        secrets_rows = secrets_result.fetchall()

        secrets: Dict[str, str] = {}
        for secret_row in secrets_rows:
            # TODO: Decrypt properly
            value = secret_row.IntegrationSecret.encrypted_value if hasattr(secret_row, "IntegrationSecret") else secret_row[0].encrypted_value  # robust row access
            field = secret_row.IntegrationSecret.field_name if hasattr(secret_row, "IntegrationSecret") else secret_row[0].field_name
            secrets[field] = value.decode("utf-8")

        # Create transport manager and driver instance
        from walnut.transports.manager import TransportManager
        transports = TransportManager(instance.config)
        try:
            driver = driver_class(instance=instance, secrets=secrets, transports=transports)

            test_result = await driver.test_connection()
            status = test_result.get("status", "unknown")
            return InstanceTestResult(
                success=(status == "connected"),
                status=status,
                latency_ms=test_result.get("latency_ms"),
                message=test_result.get("message"),
                details=test_result,
            )
        finally:
            await transports.close_all()

    except Exception as e:
        import traceback
        return InstanceTestResult(
            success=False,
            status="error",
            message=f"Connection test failed: {e}",
            details={"traceback": traceback.format_exc()}
        )
    finally:
        # Clean up imported module
        if module_name in sys.modules:
            del sys.modules[module_name]
