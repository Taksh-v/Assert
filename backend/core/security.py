import logging
from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
from cryptography.fernet import Fernet
from backend.core.config import get_settings
import json

settings = get_settings()
logger = logging.getLogger(__name__)

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# Symmetric encryption for connector tokens
# We use app_secret_key as the base for the Fernet key
# Fernet keys must be 32 url-safe base64-encoded bytes.
import base64
import hashlib

def _get_fernet_for_secret(secret: str) -> Fernet:
    """Derive a 32-byte Fernet key from the given secret string."""
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)

def _get_encryption_secret() -> str:
    """Get the primary secret key for encrypting new configurations.
    Prefer settings.app_secret_key if it is not the default placeholder.
    Otherwise, fallback to settings.supabase_jwt_secret if configured.
    Otherwise, use the default placeholder.
    """
    default_placeholder = "change-me-to-a-random-64-char-string"
    if settings.app_secret_key and settings.app_secret_key != default_placeholder:
        return settings.app_secret_key
    if settings.supabase_jwt_secret:
        return settings.supabase_jwt_secret
    return default_placeholder

def _get_fernet() -> Fernet:
    """Derive a 32-byte Fernet key from the app_secret_key."""
    return _get_fernet_for_secret(_get_encryption_secret())

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)
    return encoded_jwt

import secrets

def create_oauth_state(workspace_id: str) -> str:
    """Create a signed JWT containing the workspace_id for use as the OAuth state parameter.
    Includes a random nonce so each token is unique (prevents replay).
    Expires in 10 minutes — more than enough for an OAuth flow.
    """
    payload = {
        "workspace_id": workspace_id,
        "nonce": secrets.token_hex(16),
    }
    return create_access_token(payload, expires_delta=timedelta(minutes=10))


async def verify_oauth_state(state: str) -> str:
    """Verify the signed OAuth state JWT and return the workspace_id.
    Raises ValueError if the state is invalid, expired, or replay is detected.
    """
    try:
        payload = jwt.decode(state, settings.app_secret_key, algorithms=[ALGORITHM])
        workspace_id = payload.get("workspace_id")
        nonce = payload.get("nonce")
        if not workspace_id:
            raise ValueError("Missing workspace_id in state")
        if not nonce:
            raise ValueError("Missing nonce in state state token")

        # Verify single-use nonce in database
        from backend.core.database import async_session
        from backend.models.used_nonce import UsedNonce
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(UsedNonce).where(UsedNonce.nonce == nonce)
            res = await session.execute(stmt)
            if res.scalars().first():
                raise ValueError("State token reuse detected (nonce already used)")

            # Record used nonce
            used_nonce = UsedNonce(nonce=nonce)
            session.add(used_nonce)
            await session.commit()

        return workspace_id
    except Exception as e:
        raise ValueError(f"OAuth state verification failed: {e}")


def encrypt_config(config: dict) -> str:
    """Encrypt a configuration dictionary to a string."""
    try:
        f = _get_fernet()
        json_data = json.dumps(config).encode()
        encrypted_data = f.encrypt(json_data)
        return encrypted_data.decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise

def decrypt_config(encrypted_config: Any) -> dict:
    """Decrypt an encrypted configuration string back to a dictionary with robust fallbacks."""
    if not encrypted_config:
        return {}
        
    if isinstance(encrypted_config, dict):
        return encrypted_config
        
    if not isinstance(encrypted_config, str):
        return {}
    
    # Try the primary secret key first
    primary_secret = _get_encryption_secret()
    secrets_to_try = [primary_secret]
    
    # Add other possible secrets as fallbacks
    default_placeholder = "change-me-to-a-random-64-char-string"
    
    if settings.app_secret_key and settings.app_secret_key not in secrets_to_try:
        secrets_to_try.append(settings.app_secret_key)
        
    if settings.supabase_jwt_secret and settings.supabase_jwt_secret not in secrets_to_try:
        secrets_to_try.append(settings.supabase_jwt_secret)
        
    if default_placeholder not in secrets_to_try:
        secrets_to_try.append(default_placeholder)
        
    last_err = None
    for secret in secrets_to_try:
        try:
            f = _get_fernet_for_secret(secret)
            decrypted_data = f.decrypt(encrypted_config.encode())
            parsed = json.loads(decrypted_data.decode())
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            last_err = e
            continue
            
    # Fallback: check if it's already a plain JSON string representing a dictionary
    try:
        parsed = json.loads(encrypted_config)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    logger.error(f"Decryption failed: {last_err}")
    # SECURITY: Do NOT fall back to parsing as plain JSON.
    # If decryption fails, the config is corrupted or tampered with.
    raise ValueError(
        "Failed to decrypt connector configuration. "
        "The config may be corrupted or the encryption key may have changed. "
        "Re-authenticate the connector to fix this."
    )
