import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db
from backend.core.config import get_settings
from backend.models.connector import Connector, ConnectorType
from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from sqlalchemy import update
from backend.core.database import get_db, async_session

router = APIRouter(tags=["Connectors"])
logger = logging.getLogger(__name__)
settings = get_settings()


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
async def create_connector(request: ConnectorCreate, db: AsyncSession = Depends(get_db)):
    """
    Create or update a connector for a workspace (deduplicates by workspace+type).
    """
    from sqlalchemy import select

    w_id = await resolve_workspace_id(db, request.workspace_id)

    # Dedup: check if connector already exists for this workspace+type
    stmt = select(Connector).where(
        Connector.workspace_id == w_id,
        Connector.type == request.type
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        # Update existing connector config
        existing.config = request.config or existing.config
        existing.status = "active"
        await db.flush()
        return serialize_connector(existing)

    new_connector = Connector(
        workspace_id=w_id,
        type=request.type,
        config=request.config or {}
    )
    db.add(new_connector)
    await db.flush()
    await db.refresh(new_connector)
    
    return serialize_connector(new_connector)


@router.get("/connectors", response_model=List[ConnectorResponse])
async def list_connectors(workspace_id: str, db: AsyncSession = Depends(get_db)):
    """
    List all connectors for a workspace.
    """
    from sqlalchemy import select

    w_id = await resolve_workspace_id(db, workspace_id)
    
    stmt = select(Connector).where(Connector.workspace_id == w_id)
    result = await db.execute(stmt)
    connectors = result.scalars().all()
    
    return [serialize_connector(connector) for connector in connectors]


@router.get("/connectors/{connector_id}", response_model=ConnectorResponse)
async def get_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a single connector by ID.
    """
    from sqlalchemy import select

    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    return serialize_connector(connector)


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    """
    Disconnect and remove a connector.
    """
    from sqlalchemy import select

    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    await db.delete(connector)
    return {"status": "success", "message": f"Connector {connector_id} disconnected"}


@router.get("/connectors/{connector_id}/discover")
async def discover_source_content(connector_id: str, db: AsyncSession = Depends(get_db)):
    """
    Blueprint Layer 15: Discovery Engine.
    Lists available items (pages, folders, channels) in the connected source.
    """
    from sqlalchemy import select
    from backend.connectors.notion import NotionConnector
    from backend.connectors.google_drive import GoogleDriveConnector
    from backend.connectors.slack import SlackConnector

    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    connector_type = getattr(connector.type, "value", connector.type)

    try:
        if connector_type == "notion":
            conn_impl = NotionConnector()
        elif connector_type == "google_drive":
            conn_impl = GoogleDriveConnector()
        elif connector_type == "slack":
            conn_impl = SlackConnector()
        else:
            raise HTTPException(status_code=400, detail="Discovery not supported for this type")

        connection = await conn_impl.connect(connector.config)
        items = await conn_impl.list_resources(connection)
        return {"items": items, "total": len(items)}
    except ConnectionError as e:
        logger.error(f"Discovery failed — connection error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to browse source: {str(e)}")


@router.post("/connectors/{connector_id}/sync")
async def trigger_sync(connector_id: str, request: Optional[Dict[str, Any]] = None, db: AsyncSession = Depends(get_db)):
    """
    Trigger a sync, optionally for specific resource IDs.
    """
    from backend.ingestion.pipeline import IngestionPipeline
    from sqlalchemy import select
    
    stmt = select(Connector).where(Connector.id == connector_id)
    result = await db.execute(stmt)
    connector = result.scalars().first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
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
async def get_auth_url(source_type: str):
    """
    Generate the OAuth authorization URL for the chosen source.
    Reads credentials from .env via settings — no hardcoded values.
    """
    if source_type == "notion":
        if not settings.notion_client_id:
            raise HTTPException(status_code=500, detail="Notion OAuth not configured — set notion_client_id in .env")
        return {
            "url": (
                f"https://api.notion.com/v1/oauth/authorize"
                f"?client_id={settings.notion_client_id}"
                f"&response_type=code&owner=user"
                f"&redirect_uri={settings.notion_redirect_uri}"
            ),
            "configured": True,
        }
    
    if source_type == "google_drive":
        if not settings.google_client_id:
            raise HTTPException(status_code=500, detail="Google OAuth not configured — set google_client_id in .env")
        scope = settings.google_scopes
        return {
            "url": (
                f"https://accounts.google.com/o/oauth2/v2/auth"
                f"?client_id={settings.google_client_id}"
                f"&redirect_uri={settings.google_redirect_uri}"
                f"&response_type=code"
                f"&scope={scope}"
                f"&access_type=offline&prompt=consent"
            ),
            "configured": True,
        }
    
    if source_type == "slack":
        if settings.slack_bot_token:
            # Direct token available — no OAuth needed
            return {
                "url": None,
                "direct_token": True,
                "configured": True,
                "message": "Slack bot token found in .env — connect directly"
            }
        if not settings.slack_client_id:
            raise HTTPException(status_code=500, detail="Slack OAuth not configured — set slack_client_id or slack_bot_token in .env")
        scopes = "channels:history,channels:read,users:read"
        return {
            "url": (
                f"https://slack.com/oauth/v2/authorize"
                f"?client_id={settings.slack_client_id}"
                f"&scope={scopes}"
                f"&redirect_uri={settings.slack_redirect_uri}"
            ),
            "configured": True,
        }

    raise HTTPException(status_code=400, detail=f"OAuth not supported for '{source_type}'. Supported: notion, google_drive, slack")
