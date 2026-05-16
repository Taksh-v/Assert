import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helper: Create or update connector with OAuth tokens ──────

async def _upsert_oauth_connector(source_type: str, config: dict) -> str:
    """Create or update a connector record with OAuth tokens. Returns connector ID."""
    from backend.core.database import async_session
    from backend.models.connector import Connector
    from sqlalchemy import select
    from backend.api.connectors import resolve_workspace_id

    async with async_session() as session:
        # Resolve default workspace
        from backend.models.workspace import Workspace
        stmt = select(Workspace).where(
            (Workspace.id == "default-workspace") | (Workspace.slug == "default-workspace")
        )
        result = await session.execute(stmt)
        workspace = result.scalars().first()

        if not workspace:
            workspace = Workspace(name="Default Workspace", slug="default-workspace")
            session.add(workspace)
            await session.flush()

        workspace_id = workspace.id

        # Check if connector already exists for this workspace+type (dedup)
        stmt = select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.type == source_type
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()

        if existing:
            existing.config = config
            existing.status = "active"
            await session.commit()
            return existing.id
        else:
            new_connector = Connector(
                workspace_id=workspace_id,
                type=source_type,
                config=config,
                status="active"
            )
            session.add(new_connector)
            await session.commit()
            await session.refresh(new_connector)
            return new_connector.id


# ── OAuth Success HTML (sent to popup window) ──────────────────

def _oauth_success_html(source_type: str, connector_id: str) -> str:
    """HTML page that sends postMessage to opener and auto-closes."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connected!</title>
        <style>
            body {{
                background: #020617;
                color: white;
                font-family: 'Inter', system-ui, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }}
            .card {{
                text-align: center;
                padding: 3rem;
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 2rem;
                max-width: 400px;
            }}
            .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
            h2 {{ margin: 0 0 0.5rem; font-size: 1.5rem; }}
            p {{ color: #94A3B8; font-size: 0.875rem; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✅</div>
            <h2>Successfully Connected!</h2>
            <p>You can close this window. Redirecting back...</p>
        </div>
        <script>
            // Send message to opener (parent) window
            const data = {{
                type: 'oauth-callback',
                status: 'success',
                source_type: '{source_type}',
                connector_id: '{connector_id}'
            }};

            if (window.opener) {{
                window.opener.postMessage(data, '*');
                setTimeout(() => window.close(), 1500);
            }} else {{
                // Fallback: redirect to frontend
                window.location.href = '{settings.frontend_url}/connectors?connected={source_type}&connector_id={connector_id}';
            }}
        </script>
    </body>
    </html>
    """


def _oauth_error_html(source_type: str, error: str) -> str:
    """HTML page for OAuth errors."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connection Failed</title>
        <style>
            body {{
                background: #020617;
                color: white;
                font-family: 'Inter', system-ui, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }}
            .card {{
                text-align: center;
                padding: 3rem;
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(239,68,68,0.3);
                border-radius: 2rem;
                max-width: 400px;
            }}
            .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
            h2 {{ margin: 0 0 0.5rem; font-size: 1.5rem; color: #EF4444; }}
            p {{ color: #94A3B8; font-size: 0.875rem; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">❌</div>
            <h2>Connection Failed</h2>
            <p>{error}</p>
        </div>
        <script>
            if (window.opener) {{
                window.opener.postMessage({{
                    type: 'oauth-callback',
                    status: 'error',
                    source_type: '{source_type}',
                    error: '{error}'
                }}, '*');
                setTimeout(() => window.close(), 3000);
            }}
        </script>
    </body>
    </html>
    """


# ── Notion OAuth ──────────────────────────────────────

@router.get("/notion/login")
async def notion_login():
    """Redirect to Notion's OAuth consent page."""
    if not settings.notion_client_id:
        raise HTTPException(status_code=500, detail="Notion OAuth not configured — set notion_client_id in .env")
        
    auth_url = (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?owner=user&client_id={settings.notion_client_id}"
        f"&redirect_uri={settings.notion_redirect_uri}"
        f"&response_type=code"
    )
    return RedirectResponse(auth_url)


@router.get("/notion/callback")
async def notion_callback(code: str, request: Request):
    """Handle Notion's OAuth callback — exchange code for access_token and persist."""
    if not code:
        return HTMLResponse(_oauth_error_html("notion", "Missing authorization code"), status_code=400)
        
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            auth=(settings.notion_client_id, settings.notion_client_secret),
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.notion_redirect_uri,
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Notion OAuth error: {response.text}")
            error_detail = response.json().get("error", "Failed to exchange token")
            return HTMLResponse(_oauth_error_html("notion", error_detail), status_code=400)
            
        data = response.json()
        access_token = data.get("access_token")
        workspace_name = data.get("workspace_name", "Notion Workspace")
        workspace_id_notion = data.get("workspace_id", "")
        bot_id = data.get("bot_id", "")
        
        if not access_token:
            return HTMLResponse(_oauth_error_html("notion", "No access token received"), status_code=400)
        
        # Persist the real token in the connector config
        config = {
            "access_token": access_token,
            "workspace_name": workspace_name,
            "notion_workspace_id": workspace_id_notion,
            "bot_id": bot_id,
            "oauth": True,
        }
        
        connector_id = await _upsert_oauth_connector("notion", config)
        logger.info(f"Notion OAuth success: workspace={workspace_name}, connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("notion", connector_id))


# ── Google OAuth ──────────────────────────────────────

@router.get("/google/login")
async def google_login():
    """Redirect to Google's OAuth consent page."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured — set google_client_id and google_client_secret in .env")
        
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={settings.google_redirect_uri}"
        f"&response_type=code"
        f"&scope={settings.google_scopes}"
        f"&access_type=offline&prompt=consent"
    )
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(code: str):
    """Handle Google's OAuth callback — exchange code for tokens and persist."""
    if not code:
        return HTMLResponse(_oauth_error_html("google_drive", "Missing authorization code"), status_code=400)
        
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Google OAuth error: {response.text}")
            error_detail = response.json().get("error_description", "Failed to exchange token")
            return HTMLResponse(_oauth_error_html("google_drive", error_detail), status_code=400)
            
        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        if not access_token:
            return HTMLResponse(_oauth_error_html("google_drive", "No access token received"), status_code=400)
        
        config = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "oauth": True,
        }
        
        connector_id = await _upsert_oauth_connector("google_drive", config)
        logger.info(f"Google Drive OAuth success: connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("google_drive", connector_id))


# ── Slack OAuth ──────────────────────────────────────

@router.get("/slack/login")
async def slack_login():
    """Redirect to Slack's OAuth consent page."""
    if not settings.slack_client_id:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured — set slack_client_id in .env")
    
    scopes = "channels:history,channels:read,users:read"
    auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.slack_client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.slack_redirect_uri}"
    )
    return RedirectResponse(auth_url)


@router.get("/slack/callback")
async def slack_callback(code: str):
    """Handle Slack's OAuth callback."""
    if not code:
        return HTMLResponse(_oauth_error_html("slack", "Missing authorization code"), status_code=400)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": settings.slack_redirect_uri,
            }
        )
        
        if response.status_code != 200:
            return HTMLResponse(_oauth_error_html("slack", "Failed to exchange token"), status_code=400)
        
        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "Unknown Slack error")
            return HTMLResponse(_oauth_error_html("slack", error), status_code=400)
        
        access_token = data.get("access_token")
        team_name = data.get("team", {}).get("name", "Slack Workspace")
        
        config = {
            "access_token": access_token,
            "team_name": team_name,
            "oauth": True,
        }
        
        connector_id = await _upsert_oauth_connector("slack", config)
        logger.info(f"Slack OAuth success: team={team_name}, connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("slack", connector_id))


# ── Direct Token Setup (for connectors using bot tokens from .env) ──

@router.post("/slack/direct")
async def slack_direct_connect():
    """Connect Slack using the bot token from .env (no OAuth needed)."""
    if not settings.slack_bot_token:
        raise HTTPException(status_code=500, detail="Slack bot token not configured in .env")
    
    config = {
        "access_token": settings.slack_bot_token,
        "team_name": "Direct Bot Connection",
        "direct_token": True,
    }
    
    connector_id = await _upsert_oauth_connector("slack", config)
    return {"status": "success", "connector_id": connector_id, "message": "Slack connected via bot token"}
