import logging
from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
import bcrypt as _bcrypt
from cryptography.fernet import Fernet
from backend.core.config import get_settings
import json

settings = get_settings()
logger = logging.getLogger(__name__)

# Password hashing — using bcrypt directly (no passlib dependency)
def _bcrypt_hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

def _bcrypt_verify(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# Symmetric encryption for connector tokens
# We use app_secret_key as the base for the Fernet key
# Fernet keys must be 32 url-safe base64-encoded bytes.
import base64
import hashlib

def _get_fernet() -> Fernet:
    """Derive a 32-byte Fernet key from the app_secret_key."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret_key.encode()).digest())
    return Fernet(key)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt_verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return _bcrypt_hash(password)

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


def verify_oauth_state(state: str) -> str:
    """Verify the signed OAuth state JWT and return the workspace_id.
    Raises ValueError if the state is invalid or expired.
    """
    try:
        payload = jwt.decode(state, settings.app_secret_key, algorithms=[ALGORITHM])
        workspace_id = payload.get("workspace_id")
        if not workspace_id:
            raise ValueError("Missing workspace_id in state")
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

def decrypt_config(encrypted_config: str) -> dict:
    """Decrypt an encrypted configuration string back to a dictionary."""
    if not encrypted_config:
        return {}
    try:
        f = _get_fernet()
        decrypted_data = f.decrypt(encrypted_config.encode())
        return json.loads(decrypted_data.decode())
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        # SECURITY: Do NOT fall back to parsing as plain JSON.
        # If decryption fails, the config is corrupted or tampered with.
        raise ValueError(
            "Failed to decrypt connector configuration. "
            "The config may be corrupted or the encryption key may have changed. "
            "Re-authenticate the connector to fix this."
        )
