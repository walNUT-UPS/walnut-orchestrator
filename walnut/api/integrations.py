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
from sqlalchemy import select, join, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from walnut.auth.deps import current_active_user, require_current_user
from walnut.database.connection import get_db_session, get_db_session_dependency
from walnut.database.models import IntegrationType, IntegrationInstance, IntegrationSecret, InventoryCache
from walnut.core.integration_registry import get_integration_registry
from walnut.core.websocket_manager import get_websocket_manager  # noqa: F401  (kept for future WS broadcasts)
from walnut.core.websocket_manager import websocket_manager
import uuid
from fastapi import Query
import copy


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
    requires: Optional[Dict[str, Any]] = None
    venv_present: Optional[bool] = None


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


class IntegrationInstanceUpdate(BaseModel):
    """Integration instance update request."""
    config: Optional[Dict[str, Any]] = Field(default=None, description="Updated non-secret configuration values")
    name: Optional[str] = Field(default=None, description="Optional rename of instance")


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


# --- Action Schemas ---

class VmLifecycleRequest(BaseModel):
    verb: str = Field(..., description="Lifecycle verb: start|stop|shutdown|suspend|resume|reset")
    dry_run: bool = Field(default=False, description="If true, perform dry-run only")

class VmLifecycleResponse(BaseModel):
    ok: bool | None = None
    severity: Optional[str] = None
    task_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    reason: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    effects: Optional[Dict[str, Any]] = None


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
        # Attach venv presence by probing the filesystem path
        enriched = []
        for type_data in types:
            try:
                tp = Path(type_data.get("path") or "")
                type_data["venv_present"] = bool((tp / ".venv").exists())
            except Exception:
                type_data["venv_present"] = False
            enriched.append(IntegrationTypeOut(**type_data))
        return enriched

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integration types: {str(e)}")


@router.post("/types/upload")
async def upload_integration_package(
    file: UploadFile = File(..., description="Integration package (.int file)"),
    current_user=Depends(require_current_user),
    db: Session = Depends(get_db_session_dependency)
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
                if existing_type and (getattr(existing_type, 'status', None) or '').lower() == 'valid':
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
    db: Session = Depends(get_db_session_dependency)
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
                    if existing and (getattr(existing, 'status', None) or '').lower() == 'valid':
                        await _job_event("registry", "error", f"Integration type '{type_id}' already exists")
                        raise HTTPException(status_code=409, detail=f"Integration type '{type_id}' already exists")

                # Optional: per-plugin dependencies into a local venv in staging
                install_failed = None
                requires = manifest_data.get("requires") if isinstance(manifest_data, dict) else None
                if requires:
                    await _job_event("deps-validate", "info", "Found requires section; preparing venv")
                    venv_dir = integration_folder / ".venv"
                    deps = requires.get("deps") if isinstance(requires, dict) else None
                    wheelhouse_name = (requires.get("wheelhouse") or "wheelhouse") if isinstance(requires, dict) else None
                    wheelhouse_dir = integration_folder / str(wheelhouse_name) if wheelhouse_name else None
                    wheelhouse_exists = bool(wheelhouse_dir and wheelhouse_dir.exists())
                    if wheelhouse_name and not wheelhouse_exists:
                        await _job_event("deps-validate", "warning", f"wheelhouse '{wheelhouse_name}' not found; falling back to online installs")
                    # Create venv with pip
                    try:
                        import venv as _venv
                        def _mk():
                            builder = _venv.EnvBuilder(with_pip=True, upgrade=False, clear=False)
                            builder.create(str(venv_dir))
                        await anyio.to_thread.run_sync(_mk)
                        await _job_event("deps-install", "info", f"Created venv at {venv_dir}")
                    except Exception as _e:
                        await _job_event("deps-install", "error", f"Failed to create venv: {_e}")
                    # Install deps
                    if deps and isinstance(deps, list):
                        def _fmt(x: Any) -> str:
                            if isinstance(x, str):
                                return x
                            if isinstance(x, dict):
                                name = x.get("name", "")
                                extras = x.get("extras") or []
                                ver = x.get("version") or ""
                                markers = x.get("markers") or ""
                                es = f"[{','.join(extras)}]" if extras else ""
                                ms = f" ; {markers}" if markers else ""
                                return f"{name}{es}{ver}{ms}".strip()
                            return str(x)
                        reqs = [_fmt(d) for d in deps]
                        py_path = venv_dir / ("Scripts/python" if os.name == "nt" else "bin/python")
                        # Upgrade pip quietly (best-effort)
                        try:
                            proc_u = await asyncio.create_subprocess_exec(
                                str(py_path), "-m", "pip", "install", "--upgrade", "pip",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.STDOUT,
                                cwd=str(integration_folder),
                            )
                            if proc_u.stdout:
                                async for line in proc_u.stdout:
                                    await _job_event("deps-install", "info", line.decode(errors="ignore").rstrip())
                            await proc_u.wait()
                        except Exception:
                            pass
                        # Install requirements
                        args = [str(py_path), "-m", "pip", "install"]
                        if wheelhouse_exists:
                            args += ["--no-index", "--find-links", str(wheelhouse_dir)]
                        args += reqs
                        await _job_event("deps-install", "info", f"pip install {' '.join(reqs)}")
                        try:
                            proc_i = await asyncio.create_subprocess_exec(
                                *args,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.STDOUT,
                                cwd=str(integration_folder),
                            )
                            pip_lines: list[str] = []
                            if proc_i.stdout:
                                async for line in proc_i.stdout:
                                    text = line.decode(errors="ignore").rstrip()
                                    pip_lines.append(text)
                                    await _job_event("deps-install", "info", text)
                            rc = await proc_i.wait()
                            if rc != 0:
                                install_failed = {
                                    "code": "deps_install_error",
                                    "returncode": rc,
                                    "logs_tail": "\n".join(pip_lines)[-16000:],
                                }
                                await _job_event("deps-install", "error", f"pip failed with exit code {rc}")
                        except Exception as _e:
                            install_failed = {"code": "deps_install_error", "exception": str(_e)}
                            await _job_event("deps-install", "error", f"pip invocation failed: {_e}")

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

                # If dependency installation failed, mark invalid with error subcode immediately
                if requires and install_failed is not None:
                    from walnut.core.integration_registry import get_integration_registry as _gir
                    reg = _gir()
                    invalid = {"id": type_id, "status": "invalid", "errors": {install_failed["code"]: install_failed}}
                    try:
                        await reg._update_integration_type_status(type_id, invalid, manifest_data)  # type: ignore[attr-defined]
                    except Exception:
                        pass

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

        # Store secrets using encryptor (no-plain placeholder removal)
        if instance_data.secrets:
            try:
                from walnut.core.secrets import create_or_update_secret
                for field_name, secret_value in instance_data.secrets.items():
                    await create_or_update_secret(
                        session,
                        instance_id=instance.instance_id,
                        field_name=field_name,
                        secret_type="string",
                        value=secret_value,
                    )
            except Exception:
                # Fall back to previous behavior if encryptor not initialized
                for field_name, secret_value in instance_data.secrets.items():
                    secret = IntegrationSecret(
                        instance_id=instance.instance_id,
                        field_name=field_name,
                        secret_type="string",
                        encrypted_value=secret_value.encode("utf-8"),
                    )
                    session.add(secret)

        # Leave initial state and last_test unchanged until a real test runs

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


@router.patch("/instances/{instance_id}", response_model=IntegrationInstanceOut)
async def update_integration_instance(
    instance_id: int,
    update: IntegrationInstanceUpdate,
    current_user=Depends(require_current_user),
):
    """
    Update an integration instance's non-secret JSON config (and optional name).

    Secrets are not modified by this endpoint.
    """
    try:
        async with get_db_session() as session:
            # Load instance and type info
            stmt = (
                select(IntegrationInstance, IntegrationType)
                .join(IntegrationType, IntegrationInstance.type_id == IntegrationType.id)
                .where(IntegrationInstance.instance_id == instance_id)
            )
            result = await anyio.to_thread.run_sync(session.execute, stmt)
            row = result.first()
            if not row:
                raise HTTPException(status_code=404, detail="Integration instance not found")

            instance, type_info = row

            # Apply updates
            changed = False
            if update.name and update.name != instance.name:
                instance.name = update.name
                changed = True
            if update.config is not None:
                # Validate config against the type's connection schema (excluding secret fields)
                schema = copy.deepcopy(type_info.schema_connection or {})
                try:
                    # Prune secret fields from schema properties and required
                    props = schema.get("properties") or {}
                    non_secret_props = {k: v for k, v in props.items() if not (isinstance(v, dict) and v.get("secret") is True)}
                    schema["properties"] = non_secret_props
                    if "required" in schema and isinstance(schema["required"], list):
                        schema["required"] = [r for r in schema["required"] if r in non_secret_props]

                    # Validate using jsonschema if available
                    errors: Optional[list] = None
                    try:
                        from jsonschema import Draft202012Validator

                        validator = Draft202012Validator(schema if schema else {"type": "object"})
                        errs = list(validator.iter_errors(update.config))
                        if errs:
                            errors = [
                                {
                                    "path": ".".join(str(p) for p in e.absolute_path),
                                    "message": e.message,
                                }
                                for e in errs
                            ]
                    except Exception as _e:
                        # If jsonschema isn't available or schema invalid, fall back to type check
                        if not isinstance(update.config, dict):
                            errors = [{"path": "", "message": "config must be an object"}]

                    if errors:
                        raise HTTPException(status_code=400, detail={
                            "error": "Config validation failed",
                            "errors": errors,
                        })

                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Config validation error: {e}")

                instance.config = update.config
                # Mark for review since config changed
                instance.state = "needs_review"
                changed = True

            if changed:
                await anyio.to_thread.run_sync(session.commit)

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
                type_name=type_info.name,
                type_category=type_info.category,
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update integration instance: {str(e)}")


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
            # test_instance_connection already updates last_test, latency_ms, and state
            
            # Debug: Check if the update actually worked
            debug_query = select(IntegrationInstance).where(IntegrationInstance.instance_id == instance_id)
            debug_result = await anyio.to_thread.run_sync(session.execute, debug_query)
            debug_instance = debug_result.scalar_one_or_none()
            
            import logging
            logger = logging.getLogger(__name__)
            if debug_instance:
                logger.info(f"DEBUG: Instance {instance_id} last_test after update: {debug_instance.last_test}")
                logger.info(f"DEBUG: Instance {instance_id} latency_ms after update: {debug_instance.latency_ms}")
                logger.info(f"DEBUG: Instance {instance_id} state after update: {debug_instance.state}")
            
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


@router.get("/instances/{instance_id}/inventory")
async def get_instance_inventory(
    instance_id: int,
    type: Optional[str] = Query(None, description="Target type: vm|stack-member|port"),
    active_only: bool = Query(True, description="Only return active targets"),
    refresh: bool = Query(False, description="Force refresh, bypass cache"),
    cached_only: bool = Query(True, description="Serve only cached data; never poll drivers on this request"),
    page: Optional[int] = Query(None, description="Page number for pagination"),
    page_size: Optional[int] = Query(None, description="Page size for pagination"),
    current_user=Depends(current_active_user),
    db: Session = Depends(get_db_session_dependency)
):
    """
    List inventory targets for an integration instance with caching support.
    
    Returns paginated list of targets according to walNUT inventory contract.
    Uses database caching with configurable TTL (default 30s).
    """
    # Set defaults
    target_type = type or "vm"
    page_size = min(page_size or 100, 500)  # Cap at 500 items per page
    
    # Load instance
    instance_stmt = select(IntegrationInstance).where(IntegrationInstance.instance_id == instance_id)
    instance_result = db.execute(instance_stmt)
    instance = instance_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Integration instance not found")
    
    # Check instance status
    if instance.state == "type_unavailable":
        raise HTTPException(status_code=409, detail="Integration type is not available")
    
    # Get cached inventory with caching logic
    items = await _get_cached_inventory(
        session=db,
        instance=instance,
        target_type=target_type,
        active_only=active_only,
        force_refresh=refresh,
        cached_only=cached_only,
    )
    
    # Apply pagination if requested
    if page is not None:
        offset = (page - 1) * page_size
        paginated_items = items[offset:offset + page_size]
        
        # Generate next page token if there are more items
        next_page = None
        if len(items) > offset + page_size:
            next_page = page + 1
        
        return {
            "items": paginated_items,
            "next_page": next_page
        }
    
    return {"items": items}


@router.get("/instances/{instance_id}/inventory/summary")
async def get_instance_inventory_summary(
    instance_id: int,
    refresh: bool = Query(False, description="Force refresh, bypass cache"),
    cached_only: bool = Query(True, description="Serve only cached data; never poll drivers on this request"),
    current_user=Depends(current_active_user),
    db: Session = Depends(get_db_session_dependency)
):
    """
    Get inventory summary counts for an integration instance.
    
    Returns counts for each target type: vm, stack-member, port_active.
    """
    # Load instance
    instance_stmt = select(IntegrationInstance).where(IntegrationInstance.instance_id == instance_id)
    instance_result = db.execute(instance_stmt)
    instance = instance_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Integration instance not found")
    
    # Check instance status
    if instance.state == "type_unavailable":
        raise HTTPException(status_code=409, detail="Integration type is not available")
    
    # Get counts for each target type
    summary = {}
    
    # VM count
    vms = await _get_cached_inventory(db, instance, "vm", active_only=False, force_refresh=refresh, cached_only=cached_only)
    summary["vm"] = len(vms)
    
    # Stack member count
    stack_members = await _get_cached_inventory(db, instance, "stack-member", active_only=False, force_refresh=refresh, cached_only=cached_only)
    summary["stack_member"] = len(stack_members)
    
    # Active port count (ports where link=up OR poe=true)
    ports_active = await _get_cached_inventory(db, instance, "port", active_only=True, force_refresh=refresh, cached_only=cached_only)
    summary["port_active"] = len(ports_active)
    
    return summary


@router.post("/instances/{instance_id}/vm/{vm_id}/lifecycle", response_model=VmLifecycleResponse)
async def vm_lifecycle_action(
    instance_id: int,
    vm_id: str,
    action: VmLifecycleRequest,
    current_user=Depends(current_active_user),
):
    """
    Execute a VM lifecycle action on a Proxmox VE integration instance.

    This loads the instance driver and calls `vm_lifecycle(verb, target, dry_run)`.
    """
    async with get_db_session() as session:
        # Load instance and type
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

        # Basic guardrail: enforce capability presence
        caps = integration_type.capabilities or []
        has_vm = any((c.get("id") == "vm.lifecycle") for c in caps if isinstance(c, dict))
        if not has_vm:
            raise HTTPException(status_code=400, detail="Integration does not support vm.lifecycle")

        # Dynamically load driver
        type_path = Path(integration_type.path)
        driver_module, driver_class_name = integration_type.driver_entrypoint.split(":", 1)
        module_path = type_path / f"{driver_module}.py"
        if not module_path.exists():
            raise HTTPException(status_code=500, detail="Driver module not found")
        import importlib.util
        from walnut.core.venv_isolation import plugin_import_path
        spec = importlib.util.spec_from_file_location(f"driver_vm_{instance_id}", module_path)
        if spec is None or spec.loader is None:
            raise HTTPException(status_code=500, detail="Could not load driver module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"driver_vm_{instance_id}"] = module
        with plugin_import_path(type_path):
            spec.loader.exec_module(module)
        driver_class = getattr(module, driver_class_name, None)
        if driver_class is None:
            raise HTTPException(status_code=500, detail="Driver class not found")

        # Fetch and decrypt secrets
        try:
            from walnut.core.secrets import get_all_secrets_for_instance
            secrets: Dict[str, str] = await get_all_secrets_for_instance(session, instance_id)
        except Exception:
            # Fallback: raw bytes decode (legacy behavior)
            secrets_query = select(IntegrationSecret).where(IntegrationSecret.instance_id == instance_id)
            secrets_result = session.execute(secrets_query)
            secrets_rows = secrets_result.fetchall()
            secrets = {}
            for secret_row in secrets_rows:
                value = secret_row.IntegrationSecret.encrypted_value if hasattr(secret_row, "IntegrationSecret") else secret_row[0].encrypted_value
                field = secret_row.IntegrationSecret.field_name if hasattr(secret_row, "IntegrationSecret") else secret_row[0].field_name
                secrets[field] = value.decode("utf-8")

        from walnut.transports.manager import TransportManager
        transports = TransportManager(instance.config)
        try:
            from walnut.core.venv_isolation import plugin_import_path
            with plugin_import_path(type_path):
                driver = driver_class(instance=instance, secrets=secrets, transports=transports)
                # Minimal target shim with external_id
                target = type("T", (), {"external_id": str(vm_id)})
                res = await driver.vm_lifecycle(verb=action.verb, target=target, dry_run=action.dry_run)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"vm.lifecycle failed: {e}")
        finally:
            await transports.close_all()

        # Normalize response
        if isinstance(res, dict):
            return VmLifecycleResponse(
                ok=res.get("ok"),
                severity=res.get("severity"),
                task_id=res.get("task_id"),
                idempotency_key=res.get("idempotency_key"),
                reason=res.get("reason"),
                plan=res.get("plan"),
                effects=res.get("effects"),
            )
        return VmLifecycleResponse(ok=True)


# --- Helper Functions ---

def _normalize_target_type(t: str) -> str:
    """Normalize target type to the underscore style used by drivers/cache.
    Accepts hyphenated aliases from the UI.
    """
    if not t:
        return t
    t = t.strip()
    if t == "stack-member":
        return "stack_member"
    if t == "poe-port":
        return "port"
    return t

async def _get_cached_inventory(
    session: Session,
    instance: IntegrationInstance,
    target_type: str,
    active_only: bool,
    force_refresh: bool = False,
    cached_only: bool = False,
) -> List[Dict[str, Any]]:
    """Get inventory with caching support.
    
    Args:
        session: Database session
        instance: Integration instance
        target_type: Target type to fetch
        active_only: Whether to filter to active targets only
        force_refresh: Bypass cache and force fresh fetch
        
    Returns:
        List of inventory targets
    """
    from walnut.database.models import InventoryCache
    import time
    import logging
    logger = logging.getLogger(__name__)

    # Normalize target type for cache and driver
    requested_type = target_type
    norm_type = _normalize_target_type(target_type)

    # Check cache first (unless force refresh)
    stale_entry = None
    if not force_refresh:
        # Try both normalized and requested types for compatibility
        for t_try in (norm_type, requested_type):
            cache_stmt = select(InventoryCache).where(
                InventoryCache.instance_id == instance.instance_id,
                InventoryCache.target_type == t_try,
                InventoryCache.active_only == active_only
            )
            cache_result = session.execute(cache_stmt)
            cache_entry = cache_result.scalar_one_or_none()

            if cache_entry:
                # Check if cache is still valid
                now = datetime.now(timezone.utc)
                fetched_at = cache_entry.fetched_at
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                cache_age_seconds = (now - fetched_at).total_seconds()

                if cache_age_seconds < cache_entry.ttl_seconds:
                    return cache_entry.payload
                # Keep stale reference for potential return below
                stale_entry = cache_entry

        # If requesting active-only, fall back to cached inactive data and filter in API
        if active_only:
            for t_try in (norm_type, requested_type):
                cache_stmt2 = select(InventoryCache).where(
                    InventoryCache.instance_id == instance.instance_id,
                    InventoryCache.target_type == t_try,
                    InventoryCache.active_only == False
                )
                cache_result2 = session.execute(cache_stmt2)
                cache_entry2 = cache_result2.scalar_one_or_none()
                if cache_entry2:
                    now = datetime.now(timezone.utc)
                    fetched_at2 = cache_entry2.fetched_at
                    if fetched_at2.tzinfo is None:
                        fetched_at2 = fetched_at2.replace(tzinfo=timezone.utc)
                    cache_age_seconds2 = (now - fetched_at2).total_seconds()
                    if cache_age_seconds2 >= cache_entry2.ttl_seconds and not cached_only:
                        # Stale and not allowed to serve; continue to driver fetch
                        continue
                    items = cache_entry2.payload or []
                    # Active filter only needed for certain types (ports)
                    if norm_type == "port":
                        def _is_active_port(it: dict) -> bool:
                            a = (it or {}).get("attrs") or {}
                            link = str(a.get("link", "")).lower()
                            poe_draw = a.get("poe_power_w")
                            poe_status = str(a.get("poe_status", "")).lower()
                            return (link == "up") or (isinstance(poe_draw, (int, float)) and poe_draw > 0) or (poe_status == "delivering")
                        items = [it for it in items if _is_active_port(it)]
                    logger.info("Inventory cache hit via inactive fallback%s: type=%s count=%d",
                                " (stale)" if cache_age_seconds2 >= cache_entry2.ttl_seconds else "",
                                norm_type, len(items))
                    # If stale, schedule refresh
                    if cache_age_seconds2 >= cache_entry2.ttl_seconds:
                        try:
                            import asyncio
                            asyncio.create_task(_refresh_inventory_cache_async(instance.instance_id, norm_type, active_only))
                        except Exception:
                            pass
                    return items

    # If cached_only is requested, return stale cache if available, otherwise empty, and schedule background refresh
    if cached_only:
        if stale_entry is not None:
            logger.info("Serving stale inventory cache: type=%s active_only=%s", norm_type, active_only)
            return stale_entry.payload or []
        else:
            # No cache exists; return empty immediately (no live fetch on request path)
            logger.info("No inventory cache present; returning empty (cached_only) for type=%s active_only=%s", norm_type, active_only)
            return []
    
    # Cache miss or force refresh - fetch from driver
    start_time = time.time()
    
    try:
        # Load integration type for driver info
        type_stmt = select(IntegrationType).where(IntegrationType.id == instance.type_id)
        type_result = session.execute(type_stmt)
        integration_type = type_result.scalar_one_or_none()
        if not integration_type:
            raise Exception("Integration type not found")

        # Prefetch and decrypt secrets once (outside worker thread)
        try:
            from walnut.core.secrets import get_all_secrets_for_instance
            secrets: Dict[str, str] = await get_all_secrets_for_instance(session, instance.instance_id)
        except Exception:
            # Fallback: raw bytes decode (legacy behavior)
            secrets_query = select(IntegrationSecret).where(IntegrationSecret.instance_id == instance.instance_id)
            secrets_result = session.execute(secrets_query)
            secrets_rows = secrets_result.fetchall()
            secrets = {}
            for secret_row in secrets_rows:
                value = secret_row.IntegrationSecret.encrypted_value if hasattr(secret_row, "IntegrationSecret") else secret_row[0].encrypted_value
                field = secret_row.IntegrationSecret.field_name if hasattr(secret_row, "IntegrationSecret") else secret_row[0].field_name
                secrets[field] = value.decode("utf-8")

        # Perform driver import and inventory fetch inside a worker thread to avoid blocking the event loop
        import anyio
        def _fetch_in_thread() -> List[Dict[str, Any]]:
            import importlib.util, asyncio
            from walnut.transports.manager import TransportManager
            type_path = Path(integration_type.path)
            driver_module, driver_class_name = integration_type.driver_entrypoint.split(":", 1)
            module_path = type_path / f"{driver_module}.py"
            if not module_path.exists():
                raise Exception("Driver module not found")
            module_name = f"driver_cache_{instance.instance_id}_{int(time.time())}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise Exception("Could not load driver module")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                from walnut.core.venv_isolation import plugin_import_path
                with plugin_import_path(type_path):
                    spec.loader.exec_module(module)  # type: ignore
                driver_class = getattr(module, driver_class_name, None)
                if driver_class is None:
                    raise Exception("Driver class not found")
                transports = TransportManager(instance.config)
                try:
                    driver = driver_class(instance=instance, secrets=secrets, transports=transports)
                    async def _run() -> List[Dict[str, Any]]:
                        if not hasattr(driver, 'inventory_list'):
                            raise AttributeError(f"Driver {driver_class_name} does not have inventory_list method")
                        inventory_method = getattr(driver, 'inventory_list')
                        if not callable(inventory_method):
                            raise AttributeError(f"Driver {driver_class_name} inventory_list is not callable")
                        return await inventory_method(target_type=norm_type, active_only=active_only, options={})
                    return asyncio.run(_run())
                finally:
                    try:
                        asyncio.run(transports.close_all())
                    except Exception:
                        pass
            finally:
                # Clean up the temporary module
                try:
                    del sys.modules[module_name]
                except Exception:
                    pass

        items: List[Dict[str, Any]] = await anyio.to_thread.run_sync(_fetch_in_thread)
        
        # Calculate fetch duration
        fetch_duration_ms = int((time.time() - start_time) * 1000)
        
        # Update cache
        cache_data = {
            "instance_id": instance.instance_id,
            "target_type": norm_type,
            "active_only": active_only,
            "payload": items,
            "fetched_at": datetime.now(timezone.utc),
            "ttl_seconds": 180,  # 3 minutes TTL
            "fetch_duration_ms": fetch_duration_ms,
            "target_count": len(items)
        }
        
        # Use upsert logic - delete existing then insert new
        delete_stmt = delete(InventoryCache).where(
            InventoryCache.instance_id == instance.instance_id,
            InventoryCache.target_type == norm_type,
            InventoryCache.active_only == active_only
        )
        session.execute(delete_stmt)
        
        new_cache = InventoryCache(**cache_data)
        session.add(new_cache)
        session.commit()
        
        return items
        
    except Exception as e:
        # Return empty list on error, but log it
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to fetch inventory for instance {instance.instance_id}, type {target_type}: {e}")
        return []


async def _refresh_inventory_cache_async(instance_id: int, target_type: str, active_only: bool) -> None:
    """Background refresh of inventory cache without blocking the request thread."""
    try:
        async with get_db_session() as session:
            # Load instance
            stmt = (
                select(IntegrationInstance, IntegrationType)
                .join(IntegrationType, IntegrationInstance.type_id == IntegrationType.id)
                .where(IntegrationInstance.instance_id == instance_id)
            )
            result = await anyio.to_thread.run_sync(session.execute, stmt)
            row = result.first()
            if not row:
                return
            instance, _ = row
            # Force refresh
            await _get_cached_inventory(
                session=session,
                instance=instance,
                target_type=target_type,
                active_only=active_only,
                force_refresh=True,
                cached_only=False,
            )
    except Exception:
        # best-effort
        pass

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
    result = await anyio.to_thread.run_sync(session.execute, stmt)
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

        from walnut.core.venv_isolation import plugin_import_path
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load driver module: {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        # Keep plugin venv import path active through import and driver execution
        ctx = plugin_import_path(type_path)
        ctx.__enter__()
        try:
            spec.loader.exec_module(module)
        except Exception:
            # Ensure we exit context if import fails
            ctx.__exit__(None, None, None)
            raise

        driver_class = getattr(module, driver_class_name, None)
        if driver_class is None:
            raise RuntimeError(f"Driver class '{driver_class_name}' not found in module '{driver_module}'")

        # Get secrets (decrypted)
        try:
            from walnut.core.secrets import get_all_secrets_for_instance
            secrets: Dict[str, str] = await get_all_secrets_for_instance(session, instance_id)
        except Exception:
            # Fallback to legacy raw decode if encryptor not initialized
            secrets_query = select(IntegrationSecret).where(IntegrationSecret.instance_id == instance_id)
            secrets_result = session.execute(secrets_query)
            secrets_rows = secrets_result.fetchall()
            secrets = {}
            for secret_row in secrets_rows:
                value = secret_row.IntegrationSecret.encrypted_value if hasattr(secret_row, "IntegrationSecret") else secret_row[0].encrypted_value
                field = secret_row.IntegrationSecret.field_name if hasattr(secret_row, "IntegrationSecret") else secret_row[0].field_name
                secrets[field] = value.decode("utf-8")

        # Create transport manager and driver instance
        from walnut.transports.manager import TransportManager
        transports = TransportManager(instance.config)
        try:
            driver = driver_class(instance=instance, secrets=secrets, transports=transports)
            
            test_result = await driver.test_connection()
            status = test_result.get("status", "unknown")
            latency_ms = test_result.get("latency_ms")
            
            # Update instance with real last_test timestamp and latency
            instance.last_test = datetime.now(timezone.utc)
            instance.latency_ms = latency_ms
            
            # Update instance state based on test result
            if status == "connected":
                instance.state = "connected"
            elif status in ("degraded", "warning"):
                instance.state = "degraded"
            else:
                instance.state = "error"
            
            # Commit the updates
            session.add(instance)
            await anyio.to_thread.run_sync(session.commit)
            
            return InstanceTestResult(
                success=(status == "connected"),
                status=status,
                latency_ms=latency_ms,
                message=test_result.get("message"),
                details=test_result,
            )
        finally:
            await transports.close_all()
            # Exit plugin import path context
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass

    except Exception as e:
        import traceback
        
        # Update instance with failed test timestamp
        try:
            instance.last_test = datetime.now(timezone.utc)
            instance.latency_ms = None
            instance.state = "error"
            session.add(instance)
            await anyio.to_thread.run_sync(session.commit)
        except Exception:
            pass  # Don't let database update failures mask the original error
        
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


# --- Warm Cache Utilities ---

async def warm_inventory_cache():
    """Warm the inventory cache for all instances on startup.

    For each instance, determine supported target types and fetch them with force_refresh=True
    to populate InventoryCache, so the UI can read cached data immediately.
    """
    try:
        async with get_db_session() as session:
            # Load all instances with type capabilities
            stmt = (
                select(IntegrationInstance, IntegrationType)
                .join(IntegrationType, IntegrationInstance.type_id == IntegrationType.id)
            )
            result = await anyio.to_thread.run_sync(session.execute, stmt)
            rows = result.all()
            for instance, type_info in rows:
                try:
                    # Determine target types to warm
                    targets = set()
                    caps = type_info.capabilities or []
                    for c in caps:
                        if isinstance(c, dict) and c.get('id') == 'inventory.list':
                            for t in (c.get('targets') or []):
                                targets.add(_normalize_target_type(t))
                    # Always try 'system' where drivers support it
                    targets.add('system')
                    # Warm each target type (non-active only to cover most cases)
                    for t in targets:
                        try:
                            await _get_cached_inventory(
                                session=session,
                                instance=instance,
                                target_type=t,
                                active_only=False,
                                force_refresh=True,
                            )
                            # For ports, also warm active_only=True to eliminate UI waits
                            if t == 'port':
                                await _get_cached_inventory(
                                    session=session,
                                    instance=instance,
                                    target_type=t,
                                    active_only=True,
                                    force_refresh=True,
                                )
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        # Best-effort warmup; do not crash startup
        pass
