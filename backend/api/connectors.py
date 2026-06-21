import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import encrypt_config, decrypt_config, create_oauth_state
from backend.api.users import get_current_user
from backend.models.user import User
from backend.models.workspace_member import WorkspaceMember
from backend.models.connector import Connector, ConnectorType
from backend.models.sync_run import SyncRun
from backend.workers.sync_coordinator import ConnectorSyncCoordinator
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["Connectors"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def verify_workspace_access(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> str:
    """
    Verify that the current user has access to the specified workspace.
    Returns the workspace ID if access is granted.
    """
    # First, resolve slug if needed
    from backend.models.workspace import Workspace
    stmt = select(Workspace).where(
        (Workspace.id == workspace_id) | (Workspace.slug == workspace_id)
    )
    result = await db.execute(stmt)
    workspace = result.scalars().first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found. Create it first via POST /api/workspaces.")
    
    # Check membership
    stmt = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == current_user.id
    )
    result = await db.execute(stmt)
    membership = result.scalars().first()
    
    if not membership:
        if not settings.is_development:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not a member of this workspace."
            )
            
        from backend.models.workspace_member import WorkspaceRole
        membership = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role=WorkspaceRole.OWNER
        )
        db.add(membership)
        await db.commit()
    
    return workspace.id


async def resolve_workspace_id(db: AsyncSession, workspace_ref: str) -> str:
    from backend.models.workspace import Workspace
    from sqlalchemy import select

    stmt = select(Workspace).where(
        (Workspace.id == workspace_ref) | (Workspace.slug == workspace_ref)
    )
    result = await db.execute(stmt)
    workspace = result.scalars().first()
    if workspace:
        return workspace.id

    raise HTTPException(status_code=404, detail="Workspace not found. Create it first via POST /api/workspaces.")


class ConnectorCreate(BaseModel):
    workspace_id: str
    type: ConnectorType
    config: Dict[str, Any]


class SyncRunSummary(BaseModel):
    id: str
    status: str
    triggered_by: str
    stats: Dict[str, Any] = {}
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SyncRunResponse(SyncRunSummary):
    connector_id: str
    workspace_id: str
    selected_ids: Optional[List[str]] = None
    task_id: Optional[str] = None


class SyncTriggerResponse(BaseModel):
    sync_run_id: str
    status: str
    message: str


class ConnectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    type: ConnectorType
    status: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    config_summary: Dict[str, Any] = {}
    document_count: int = 0
    latest_sync: Optional[SyncRunSummary] = None


def serialize_sync_run(sync_run: Optional[SyncRun]) -> Optional[SyncRunSummary]:
    if not sync_run:
        return None
    return SyncRunSummary(
        id=sync_run.id,
        status=sync_run.status,
        triggered_by=sync_run.triggered_by,
        stats=sync_run.stats or {},
        error=sync_run.error,
        created_at=sync_run.created_at,
        started_at=sync_run.started_at,
        completed_at=sync_run.completed_at,
    )


def serialize_sync_run_response(sync_run: SyncRun) -> SyncRunResponse:
    summary = serialize_sync_run(sync_run)
    return SyncRunResponse(
        **summary.model_dump(),
        connector_id=sync_run.connector_id,
        workspace_id=sync_run.workspace_id,
        selected_ids=sync_run.selected_ids,
        task_id=sync_run.task_id,
    )


def serialize_connector(connector: Connector, latest_sync: Optional[SyncRun] = None) -> ConnectorResponse:
    # Decrypt config for internal use, but safe summary filters it
    decryption_failed = False
    try:
        config = decrypt_config(connector.config)
        if not isinstance(config, dict):
            config = {}
            decryption_failed = True
    except Exception:
        config = {}
        decryption_failed = True
        
    # Safe summary: expose non-sensitive config fields only
    safe_keys = {"workspace_name", "team_name", "folder_id", "channels", "oauth", "direct_token"}
    config_summary = {
        key: value
        for key, value in config.items()
        if key in safe_keys
    }
    if decryption_failed:
        config_summary["decryption_failed"] = True

    status = getattr(connector.status, "value", connector.status)
    if decryption_failed:
        status = "error"

    sync_summary = serialize_sync_run(latest_sync)
    if decryption_failed:
        decryption_error_msg = (
            "Config decryption failed: Failed to decrypt connector configuration. "
            "The config may be corrupted or the encryption key may have changed. "
            "Re-authenticate the connector to fix this."
        )
        if not sync_summary:
            sync_summary = SyncRunSummary(
                id="decryption-failed-placeholder",
                status="failed",
                triggered_by="system",
                error=decryption_error_msg,
                created_at=datetime.utcnow()
            )
        elif not sync_summary.error:
            sync_summary.error = decryption_error_msg
            sync_summary.status = "failed"

    return ConnectorResponse(
        id=connector.id,
        workspace_id=connector.workspace_id,
        type=connector.type,
        status=status,
        last_synced_at=connector.last_synced_at,
        created_at=connector.created_at,
        config_summary=config_summary,
        latest_sync=sync_summary,
    )


async def _latest_sync_for_connector(db: AsyncSession, connector_id: str) -> Optional[SyncRun]:
    return await ConnectorSyncCoordinator().get_latest_sync_run(db, connector_id)


@router.post("/connectors", response_model=ConnectorResponse)
async def create_connector(
    request: ConnectorCreate, 
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Depends(verify_workspace_access)
):
    """
    Create or update a connector for a workspace. 
    Configs are stored encrypted in the database.
    """
    from sqlalchemy import select

    import uuid

    # Dedup: check if connector already exists for this workspace+type
    stmt = select(Connector).where(
        Connector.workspace_id == workspace_id,
        Connector.type == request.type
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    connector_id = existing.id if existing else str(uuid.uuid4())
    
    # Auto configure local storage for manually uploaded files
    if request.type == ConnectorType.FILE_UPLOAD:
        upload_dir = f"data/uploads/{workspace_id}/{connector_id}"
        request.config = {"upload_dir": upload_dir}

    encrypted_config = encrypt_config(request.config or {})

    if existing:
        # Update existing connector config
        existing.config = encrypted_config
        existing.status = "active"
        await db.commit()
        return serialize_connector(existing, await _latest_sync_for_connector(db, existing.id))

    new_connector = Connector(
        id=connector_id,
        workspace_id=workspace_id,
        type=request.type,
        config=encrypted_config
    )
    db.add(new_connector)
    await db.commit()
    await db.refresh(new_connector)
    
    return serialize_connector(new_connector)


@router.get("/connectors", response_model=List[ConnectorResponse])
async def list_connectors(
    workspace_id: str = Depends(verify_workspace_access), 
    db: AsyncSession = Depends(get_db)
):
    """
    List all connectors for a workspace.
    Uses a batched query for latest sync runs to avoid N+1.
    """
    from sqlalchemy import select, func

    stmt = select(Connector).where(Connector.workspace_id == workspace_id)
    result = await db.execute(stmt)
    connectors = result.scalars().all()
    
    if not connectors:
        return []

    # Batch fetch: get the latest sync run for ALL connectors in 1 query
    # Subquery finds max(created_at) per connector_id
    connector_ids = [c.id for c in connectors]
    latest_subq = (
        select(
            SyncRun.connector_id,
            func.max(SyncRun.created_at).label("max_created")
        )
        .where(SyncRun.connector_id.in_(connector_ids))
        .group_by(SyncRun.connector_id)
        .subquery()
    )
    # Join back to get the full SyncRun rows
    sync_stmt = (
        select(SyncRun)
        .join(
            latest_subq,
            (SyncRun.connector_id == latest_subq.c.connector_id)
            & (SyncRun.created_at == latest_subq.c.max_created)
        )
    )
    sync_result = await db.execute(sync_stmt)
    sync_runs_by_connector = {sr.connector_id: sr for sr in sync_result.scalars().all()}

    responses = []
    for connector in connectors:
        responses.append(serialize_connector(connector, sync_runs_by_connector.get(connector.id)))
    return responses


@router.get("/connectors/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a single connector by ID, verifying access.
    """
    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Verify access to the workspace
    await verify_workspace_access(connector.workspace_id, db, current_user)

    return serialize_connector(connector, await _latest_sync_for_connector(db, connector.id))


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Disconnect and remove a connector.
    """
    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Verify access
    await verify_workspace_access(connector.workspace_id, db, current_user)

    await db.delete(connector)
    await db.commit()
    return {"status": "success", "message": f"Connector {connector_id} disconnected"}


@router.get("/connectors/{connector_id}/discover")
async def discover_source_content(
    connector_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Blueprint Layer 15: Discovery Engine.
    Lists available items (pages, folders, channels) in the connected source.
    """
    from backend.connectors.registry import connector_factory

    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Verify access
    await verify_workspace_access(connector.workspace_id, db, current_user)

    connector_type = getattr(connector.type, "value", connector.type)

    try:
        conn_impl = connector_factory.create(connector_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Discovery not supported for this type")

    try:
        # Use decrypted config for connection
        config = decrypt_config(connector.config)
        connection = await conn_impl.connect(config)
        items = await conn_impl.list_resources(connection)
        return {"items": items, "total": len(items)}
    except ConnectionError as e:
        logger.error(f"Discovery failed — connection error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to browse source: {str(e)}")


@router.post(
    "/connectors/{connector_id}/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SyncTriggerResponse,
)
async def trigger_sync(
    connector_id: str, 
    request: Optional[Dict[str, Any]] = None, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a sync, optionally for specific resource IDs.
    """
    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Verify access
    await verify_workspace_access(connector.workspace_id, db, current_user)
    
    selected_ids = request.get("selected_ids") if request else None

    from backend.workers.task_queue import enqueue_task

    coordinator = ConnectorSyncCoordinator()
    sync_run, created = await coordinator.create_sync_run(
        db,
        connector,
        selected_ids=selected_ids,
        triggered_by="manual",
    )
    if created:
        task_id = await enqueue_task("connector_sync", {"sync_run_id": sync_run.id}, db=db)
        await coordinator.attach_task(db, sync_run, task_id)
        await db.commit()

    return {
        "sync_run_id": sync_run.id,
        "status": sync_run.status,
        "message": "Sync started" if created else "Sync already running",
    }


@router.get("/connectors/{connector_id}/sync-runs/latest", response_model=Optional[SyncRunResponse])
async def get_latest_connector_sync_run(
    connector_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Connector).where(Connector.id == connector_id)
    connector = (await db.execute(stmt)).scalars().first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    await verify_workspace_access(connector.workspace_id, db, current_user)
    sync_run = await ConnectorSyncCoordinator().get_latest_sync_run(db, connector_id)
    return serialize_sync_run_response(sync_run) if sync_run else None


@router.get("/sync-runs/{sync_run_id}", response_model=SyncRunResponse)
async def get_sync_run(
    sync_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sync_run = (await db.execute(select(SyncRun).where(SyncRun.id == sync_run_id))).scalars().first()
    if not sync_run:
        raise HTTPException(status_code=404, detail="Sync run not found")

    await verify_workspace_access(sync_run.workspace_id, db, current_user)
    return serialize_sync_run_response(sync_run)


@router.get("/oauth/authorize/{source_type}")
async def get_auth_url(
    source_type: str,
    workspace_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Generate the OAuth authorization URL for the chosen source.
    Reads credentials from .env via settings. Raises 400 if not configured.
    """
    if source_type == "notion":
        if not settings.notion_client_id:
            raise HTTPException(status_code=400, detail="Notion OAuth is not configured. Please set NOTION_CLIENT_ID in .env")
        return {
            "url": (
                f"https://api.notion.com/v1/oauth/authorize"
                f"?client_id={settings.notion_client_id}"
                f"&response_type=code&owner=user"
                f"&redirect_uri={settings.notion_redirect_uri}"
                f"&state={create_oauth_state(workspace_id or 'default-workspace')}"
            ),
            "configured": True,
        }
    
    if source_type == "google_drive":
        if not settings.google_client_id:
            raise HTTPException(status_code=400, detail="Google Drive OAuth is not configured. Please set GOOGLE_CLIENT_ID in .env")
        scope = settings.google_scopes
        return {
            "url": (
                f"https://accounts.google.com/o/oauth2/v2/auth"
                f"?client_id={settings.google_client_id}"
                f"&redirect_uri={settings.google_redirect_uri}"
                f"&response_type=code"
                f"&scope={scope}"
                f"&access_type=offline&prompt=consent"
                f"&state={create_oauth_state(workspace_id or 'default-workspace')}"
            ),
            "configured": True,
        }
    
    if source_type == "slack":
        if settings.slack_bot_token and not settings.slack_client_id:
            return {"direct_token": True, "configured": True}
        if not settings.slack_client_id:
            raise HTTPException(status_code=400, detail="Slack OAuth is not configured. Please set SLACK_CLIENT_ID in .env")
        scopes = "channels:history,channels:read,users:read"
        return {
            "url": (
                f"https://slack.com/oauth/v2/authorize"
                f"?client_id={settings.slack_client_id}"
                f"&scope={scopes}"
                f"&redirect_uri={settings.slack_redirect_uri}"
                f"&state={create_oauth_state(workspace_id or 'default-workspace')}"
            ),
            "configured": True,
        }

    raise HTTPException(status_code=400, detail=f"OAuth not supported for '{source_type}'. Supported: notion, google_drive, slack")


@router.post("/connectors/{connector_id}/upload")
async def upload_file(
    connector_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    import os

    # 1. Fetch connector & check workspace access
    stmt = select(Connector).where(Connector.id == connector_id)
    connector = (await db.execute(stmt)).scalars().first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
        
    await verify_workspace_access(connector.workspace_id, db, current_user)
    
    # 2. Get upload directory path
    try:
        config = decrypt_config(connector.config)
    except:
        config = {}
        
    upload_dir = config.get("upload_dir")
    if not upload_dir:
        # Reconstruct path if missing
        upload_dir = f"data/uploads/{connector.workspace_id}/{connector.id}"
        config["upload_dir"] = upload_dir
        connector.config = encrypt_config(config)
        await db.commit()
        
    # Create dir if not exists
    os.makedirs(upload_dir, exist_ok=True)
    
    # 3. Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid file name")
        
    file_path = os.path.join(upload_dir, safe_filename)
    
    # 4. Read file content and enforce strict 50MB limit before writing to disk
    MAX_BYTES = 50 * 1024 * 1024  # 50 MB
    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds maximum ingestion limit (50MB)"
        )

    # 5. Save file bytes to upload directory
    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    return {"status": "success", "filename": safe_filename}
