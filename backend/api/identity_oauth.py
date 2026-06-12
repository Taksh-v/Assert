import logging
import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import create_access_token
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
from typing import Optional

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/identity", tags=["Identity OAuth"])

async def _get_or_create_oauth_user(db: AsyncSession, email: str, full_name: str) -> User:
    """Helper to upsert a user and ensure they have a workspace."""
    # Check by email (this implementation doesn't use supabase_id yet since it's custom OAuth)
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        # Create user with a dummy password since they use OAuth
        user = User(
            email=email,
            hashed_password="oauth-protected-" + str(uuid.uuid4()),
            full_name=full_name,
            is_active=True
        )
        db.add(user)
        await db.flush()
        
        # Create personal workspace
        workspace_name = f"{full_name or email.split('@')[0]}'s Workspace"
        slug = f"workspace-{user.id[:8]}"
        new_workspace = Workspace(name=workspace_name, slug=slug)
        db.add(new_workspace)
        await db.flush()
        
        # Add user as OWNER
        membership = WorkspaceMember(
            workspace_id=new_workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER
        )
        db.add(membership)
        await db.commit()
    
    return user

def _oauth_success_html(token: str) -> str:
    """Return HTML that passes the token to the parent window and closes itself."""
    return f"""
    <html>
        <head><title>Success</title></head>
        <body>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'oauth-identity-success',
                        token: '{token}'
                    }}, '*');
                    setTimeout(() => window.close(), 1000);
                }} else {{
                    document.body.innerHTML = 'Logged in successfully. You can close this tab.';
                }}
            </script>
            <p style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                Authentication successful! Redirecting...
            </p>
        </body>
    </html>
    """

# ── Google Identity ─────────────────────────────────────
@router.get("/google/login")
async def google_identity_login():
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    # Use a different scope for identity than the connector
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={settings.google_identity_redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(auth_url)

@router.get("/google/callback")
async def google_identity_callback(code: str, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_identity_redirect_uri,
            }
        )
        if token_res.status_code != 200:
            return HTMLResponse(f"Failed to exchange Google token: {token_res.text}", status_code=400)
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        # Fetch user profile
        profile_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        profile = profile_res.json()
        email = profile.get("email")
        name = profile.get("name")
        
        if not email:
            return HTMLResponse("No email received from Google", status_code=400)
        
        user = await _get_or_create_oauth_user(db, email, name)
        jwt_token = create_access_token(data={"sub": user.id})
        return HTMLResponse(_oauth_success_html(jwt_token))

# ── GitHub Identity ─────────────────────────────────────
@router.get("/github/login")
async def github_identity_login():
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")
    
    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope=user:email"
        f"&redirect_uri={settings.github_redirect_uri}"
    )
    return RedirectResponse(auth_url)

@router.get("/github/callback")
async def github_identity_callback(code: str, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        # Exchange code
        token_res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            }
        )
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        # Fetch user
        user_res = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {access_token}"}
        )
        user_data = user_res.json()
        
        # GitHub might not return email in primary profile if it's private
        email = user_data.get("email")
        if not email:
            emails_res = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"token {access_token}"}
            )
            emails = emails_res.json()
            primary_email = next((e for e in emails if e.get("primary")), emails[0])
            email = primary_email.get("email")
        
        user = await _get_or_create_oauth_user(db, email, user_data.get("name") or user_data.get("login"))
        jwt_token = create_access_token(data={"sub": user.id})
        return HTMLResponse(_oauth_success_html(jwt_token))

# ── Facebook Identity ───────────────────────────────────
@router.get("/facebook/login")
async def facebook_identity_login():
    if not settings.facebook_client_id:
        raise HTTPException(status_code=500, detail="Facebook OAuth not configured")
    
    auth_url = (
        f"https://www.facebook.com/v12.0/dialog/oauth"
        f"?client_id={settings.facebook_client_id}"
        f"&redirect_uri={settings.facebook_redirect_uri}"
        f"&scope=email,public_profile"
    )
    return RedirectResponse(auth_url)

@router.get("/facebook/callback")
async def facebook_identity_callback(code: str, db: AsyncSession = Depends(get_db)):
    return HTMLResponse("Facebook OAuth callback is currently under construction. Please use Google or GitHub.", status_code=501)
