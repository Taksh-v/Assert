import logging
import secrets
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.security import create_access_token, create_oauth_state, verify_oauth_state
from backend.api.users import get_current_user
from backend.models.user import User
from jose import jwt, JWTError
from datetime import timedelta

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_oauth_state(workspace_id: str) -> str:
    """Create a signed JWT containing the workspace_id for use as the OAuth state parameter."""
    return create_oauth_state(workspace_id)


def _verify_oauth_state(state: str) -> str:
    """Verify the signed OAuth state JWT and return the workspace_id."""
    try:
        return verify_oauth_state(state)
    except ValueError as e:
        logger.warning(f"OAuth state verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state token")


# ── Helper: Create or update connector with OAuth tokens ──────

async def _upsert_oauth_connector(source_type: str, workspace_id: str, config: dict) -> str:
    """Create or update a connector record with OAuth tokens for a specific workspace."""
    from backend.core.database import async_session
    from backend.models.connector import Connector
    from backend.models.workspace import Workspace
    from sqlalchemy import select
    from backend.core.security import encrypt_config

    async with async_session() as session:
        # Resolve workspace_id to actual UUID (handles slug)
        stmt = select(Workspace).where(
            (Workspace.id == workspace_id) | (Workspace.slug == workspace_id)
        )
        result = await session.execute(stmt)
        workspace = result.scalars().first()
        
        if not workspace:
            raise Exception(f"Workspace {workspace_id} not found. Create it first via POST /api/workspaces.")
        
        resolved_w_id = workspace.id

        # Check if connector already exists for this workspace+type (dedup)
        stmt = select(Connector).where(
            Connector.workspace_id == resolved_w_id,
            Connector.type == source_type
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()

        encrypted_config = encrypt_config(config)

        if existing:
            existing.config = encrypted_config
            existing.status = "active"
            await session.commit()
            return existing.id
        else:
            new_connector = Connector(
                workspace_id=resolved_w_id,
                type=source_type,
                config=encrypted_config,
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
async def notion_login(workspace_id: str):
    """Redirect to Notion's OAuth consent page."""
    if not settings.notion_client_id:
        raise HTTPException(status_code=500, detail="Notion OAuth not configured")
        
    state_token = _create_oauth_state(workspace_id)
    auth_url = (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?owner=user&client_id={settings.notion_client_id}"
        f"&redirect_uri={settings.notion_redirect_uri}"
        f"&response_type=code"
        f"&state={state_token}"
    )
    return RedirectResponse(auth_url)


@router.get("/notion/callback")
async def notion_callback(code: str, state: str, request: Request):
    """Handle Notion's OAuth callback."""
    if not code:
        return HTMLResponse(_oauth_error_html("notion", "Missing authorization code"), status_code=400)
    
    # SECURITY: Verify the signed state token to prevent CSRF
    workspace_id = _verify_oauth_state(state)
        
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
        
        connector_id = await _upsert_oauth_connector("notion", workspace_id, config)
        logger.info(f"Notion OAuth success: workspace={workspace_name}, connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("notion", connector_id))


# ── Google OAuth ──────────────────────────────────────

@router.get("/google/login")
async def google_login(workspace_id: str):
    """Redirect to Google's OAuth consent page."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
    state_token = _create_oauth_state(workspace_id)
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={settings.google_redirect_uri}"
        f"&response_type=code"
        f"&scope={settings.google_scopes}"
        f"&state={state_token}"
        f"&access_type=offline&prompt=consent"
    )
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(code: str, state: str):
    """Handle Google's OAuth callback."""
    if not code:
        return HTMLResponse(_oauth_error_html("google_drive", "Missing authorization code"), status_code=400)
    
    # SECURITY: Verify the signed state token to prevent CSRF
    workspace_id = _verify_oauth_state(state)
        
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
        
        connector_id = await _upsert_oauth_connector("google_drive", workspace_id, config)
        logger.info(f"Google Drive OAuth success: connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("google_drive", connector_id))


# ── Slack OAuth ──────────────────────────────────────

@router.get("/slack/login")
async def slack_login(workspace_id: str):
    """Redirect to Slack's OAuth consent page."""
    if not settings.slack_client_id:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")
    
    state_token = _create_oauth_state(workspace_id)
    scopes = "channels:history,channels:read,users:read"
    auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.slack_client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.slack_redirect_uri}"
        f"&state={state_token}"
    )
    return RedirectResponse(auth_url)


@router.get("/slack/callback")
async def slack_callback(code: str, state: str):
    """Handle Slack's OAuth callback."""
    if not code:
        return HTMLResponse(_oauth_error_html("slack", "Missing authorization code"), status_code=400)

    if not settings.slack_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Slack OAuth is not configured. Please set SLACK_CLIENT_SECRET in .env",
        )
    
    # SECURITY: Verify the signed state token to prevent CSRF
    workspace_id = _verify_oauth_state(state)
    
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
            if error == "bad_client_secret":
                error = (
                    "Slack rejected the client secret. Verify SLACK_CLIENT_SECRET in .env "
                    "is the OAuth Client Secret from the Slack app, not the Signing Secret."
                )
            return HTMLResponse(_oauth_error_html("slack", error), status_code=400)
        
        access_token = data.get("access_token")
        team_name = data.get("team", {}).get("name", "Slack Workspace")
        
        config = {
            "access_token": access_token,
            "team_name": team_name,
            "oauth": True,
        }
        
        connector_id = await _upsert_oauth_connector("slack", workspace_id, config)
        logger.info(f"Slack OAuth success: team={team_name}, connector_id={connector_id}")
        
        return HTMLResponse(_oauth_success_html("slack", connector_id))


@router.post("/slack/direct")
async def slack_direct(workspace_id: str, current_user: User = Depends(get_current_user)):
    """Create or update a Slack connector from the configured bot token."""
    if not settings.slack_bot_token:
        raise HTTPException(
            status_code=400,
            detail="Slack direct token is not configured. Please set SLACK_BOT_TOKEN in .env",
        )

    config = {
        "access_token": settings.slack_bot_token,
        "team_name": "Slack Workspace",
        "direct_token": True,
    }
    connector_id = await _upsert_oauth_connector("slack", workspace_id, config)
    logger.info(f"Slack direct token connector ready: connector_id={connector_id}")
    return {"connector_id": connector_id, "status": "connected"}


