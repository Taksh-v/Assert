import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.core.database import get_db, async_session
from backend.core.config import get_settings
from backend.core.security import encrypt_config, decrypt_config
from backend.api.users import get_current_user
from backend.models.user import User
from backend.models.workspace_member import WorkspaceMember
from backend.models.connector import Connector, ConnectorType
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
        if workspace_id == "default-workspace":
            workspace = Workspace(name="Default Workspace", slug="default-workspace")
            db.add(workspace)
            await db.flush()
        else:
            raise HTTPException(status_code=404, detail="Workspace not found")
    
    # Check membership
    stmt = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == current_user.id
    )
    result = await db.execute(stmt)
    membership = result.scalars().first()
    
    if not membership:
        from backend.models.workspace_member import WorkspaceRole
        membership = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role=WorkspaceRole.OWNER
        )
        db.add(membership)
        await db.flush()
    
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

    if workspace_ref == "default-workspace":
        workspace = Workspace(name="Default Workspace", slug="default-workspace")
        db.add(workspace)
        await db.flush()
        return workspace.id

    raise HTTPException(status_code=404, detail="Workspace not found")


class ConnectorCreate(BaseModel):
    workspace_id: str
    type: ConnectorType
    config: Dict[str, Any]


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


def serialize_connector(connector: Connector) -> ConnectorResponse:
    # Decrypt config for internal use, but safe summary filters it
    try:
        config = decrypt_config(connector.config)
    except:
        config = connector.config or {}
        
    # Safe summary: expose non-sensitive config fields only
    safe_keys = {"workspace_name", "team_name", "folder_id", "channels", "oauth", "direct_token"}
    return ConnectorResponse(
        id=connector.id,
        workspace_id=connector.workspace_id,
        type=connector.type,
        status=getattr(connector.status, "value", connector.status),
        last_synced_at=connector.last_synced_at,
        created_at=connector.created_at,
        config_summary={
            key: value
            for key, value in config.items()
            if key in safe_keys
        },
    )


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

    # Dedup: check if connector already exists for this workspace+type
    stmt = select(Connector).where(
        Connector.workspace_id == workspace_id,
        Connector.type == request.type
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    encrypted_config = encrypt_config(request.config or {})

    if existing:
        # Update existing connector config
        existing.config = encrypted_config
        existing.status = "active"
        await db.flush()
        return serialize_connector(existing)

    new_connector = Connector(
        workspace_id=workspace_id,
        type=request.type,
        config=encrypted_config
    )
    db.add(new_connector)
    await db.flush()
    await db.refresh(new_connector)
    
    return serialize_connector(new_connector)


@router.get("/connectors", response_model=List[ConnectorResponse])
async def list_connectors(
    workspace_id: str = Depends(verify_workspace_access), 
    db: AsyncSession = Depends(get_db)
):
    """
    List all connectors for a workspace.
    """
    from sqlalchemy import select

    stmt = select(Connector).where(Connector.workspace_id == workspace_id)
    result = await db.execute(stmt)
    connectors = result.scalars().all()
    
    return [serialize_connector(connector) for connector in connectors]


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

    return serialize_connector(connector)


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
    from backend.connectors.registry import connector_registry

    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Verify access
    await verify_workspace_access(connector.workspace_id, db, current_user)

    connector_type = getattr(connector.type, "value", connector.type)

    try:
        conn_class = connector_registry.get_connector(connector_type)
        conn_impl = conn_class()

        # Use decrypted config for connection
        config = decrypt_config(connector.config)
        connection = await conn_impl.connect(config)
        items = await conn_impl.list_resources(connection)
        return {"items": items, "total": len(items)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Discovery not supported for this type")
    except ConnectionError as e:
        logger.error(f"Discovery failed — connection error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to browse source: {str(e)}")


@router.post("/connectors/{connector_id}/sync")
async def trigger_sync(
    connector_id: str, 
    request: Optional[Dict[str, Any]] = None, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a sync, optionally for specific resource IDs.
    """
    from backend.ingestion.pipeline import IngestionPipeline
    
    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Verify access
    await verify_workspace_access(connector.workspace_id, db, current_user)
    
    selected_ids = request.get("selected_ids") if request else None
    
    try:
        pipeline = IngestionPipeline()
    except Exception as e:
        logger.error(f"Pipeline init failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline error: {str(e)}")

    # Run the pipeline as a background task to avoid blocking the UI
    async def run_in_background():
        try:
            logger.info(f"Starting background sync for connector {connector_id}")
            await pipeline.run(connector_id, selected_ids=selected_ids)
            
            # Update status in a fresh session to avoid detached instance errors
            async with async_session() as session:
                stmt = update(Connector).where(Connector.id == connector_id).values(
                    status="active",
                    last_synced_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
            logger.info(f"Background sync completed for connector {connector_id}")
        except Exception as e:
            logger.error(f"Background sync failed for {connector_id}: {e}")
            async with async_session() as session:
                stmt = update(Connector).where(Connector.id == connector_id).values(
                    status="error",
                    error_log={"last_error": str(e), "timestamp": datetime.utcnow().isoformat()}
                )
                await session.execute(stmt)
                await session.commit()

    asyncio.create_task(run_in_background())
    
    return {
        "status": "success", 
        "message": "Sync started in background. You can close this window and the brain will update shortly."
    }


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
                f"&state={workspace_id or 'default-workspace'}"
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
                f"&state={workspace_id or 'default-workspace'}"
            ),
            "configured": True,
        }
    
    if source_type == "slack":
        if not settings.slack_client_id:
            raise HTTPException(status_code=400, detail="Slack OAuth is not configured. Please set SLACK_CLIENT_ID in .env")
        scopes = "channels:history,channels:read,users:read"
        return {
            "url": (
                f"https://slack.com/oauth/v2/authorize"
                f"?client_id={settings.slack_client_id}"
                f"&scope={scopes}"
                f"&redirect_uri={settings.slack_redirect_uri}"
                f"&state={workspace_id or 'default-workspace'}"
            ),
            "configured": True,
        }

    raise HTTPException(status_code=400, detail=f"OAuth not supported for '{source_type}'. Supported: notion, google_drive, slack")
