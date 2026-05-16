import logging
import hashlib
import hmac
import time
from fastapi import APIRouter, Request, Header, BackgroundTasks, HTTPException
from backend.ingestion.pipeline import IngestionPipeline
from backend.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


async def verify_slack_signature(request: Request, x_slack_signature: str, x_slack_request_timestamp: str):
    """
    Verify that the request is coming from Slack.
    """
    if not x_slack_signature or not x_slack_request_timestamp:
        raise HTTPException(status_code=401, detail="Missing Slack signature headers")
    
    # Check if the request is too old (replay attack protection)
    if abs(time.time() - int(x_slack_request_timestamp)) > 60 * 5:
        raise HTTPException(status_code=401, detail="Slack request too old")
    
    request_body = await request.body()
    sig_basestring = f"v0:{x_slack_request_timestamp}:{request_body.decode('utf-8')}"
    
    # Slack signing secret should be in env
    slack_signing_secret = getattr(settings, "slack_signing_secret", "assest_slack_secret")
    
    my_signature = "v0=" + hmac.new(
        slack_signing_secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(my_signature, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


from backend.core.database import async_session
from backend.models.connector import Connector
from sqlalchemy import select

@router.post("/slack")
async def slack_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_slack_signature: str = Header(None),
    x_slack_request_timestamp: str = Header(None)
):
    """
    Blueprint Layer 1: Event-Driven Ingestion.
    Handles real-time Slack messages and events.
    """
    # 1. URL Verification (Initial Setup)
    data = await request.json()
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    
    # 2. Security Check (Production)
    # await verify_slack_signature(request, x_slack_signature, x_slack_request_timestamp)
    
    # 3. Handle Events
    event = data.get("event", {})
    event_type = event.get("type")
    team_id = data.get("team_id")
    
    logger.info(f"Received Slack event: {event_type} for team: {team_id}")
    
    if event_type == "message" and not event.get("bot_id"):
        # Find the Slack connector for this team
        async with async_session() as session:
            stmt = select(Connector).where(Connector.type == "slack")
            # In production, we'd filter by team_id inside Connector.config
            result = await session.execute(stmt)
            connector = result.scalars().first()
            
            if connector:
                logger.info(f"Triggering micro-ingest for Slack connector: {connector.id}")
                pipeline = IngestionPipeline()
                background_tasks.add_task(pipeline.run, connector_id=connector.id)
    
    return {"status": "ok"}


@router.post("/notion")
async def notion_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handles real-time Notion page updates.
    """
    data = await request.json()
    logger.info(f"Received Notion webhook: {data}")
    
    # Find the Notion connector
    async with async_session() as session:
        stmt = select(Connector).where(Connector.type == "notion")
        result = await session.execute(stmt)
        connector = result.scalars().first()
        
        if connector:
            pipeline = IngestionPipeline()
            background_tasks.add_task(pipeline.run, connector_id=connector.id)
    
    return {"status": "ok"}

