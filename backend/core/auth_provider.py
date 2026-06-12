from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
from jose import jwt, JWTError
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

@dataclass
class UserAuthPayload:
    user_id: str
    email: str
    full_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AuthProvider(ABC):
    @abstractmethod
    async def verify_token(self, token: str) -> Optional[UserAuthPayload]:
        """Verify the authentication token and return a UserAuthPayload if valid."""
        pass

class SupabaseAuthProvider(AuthProvider):
    def __init__(self, jwt_secret: Optional[str] = None):
        self.jwt_secret = jwt_secret or settings.supabase_jwt_secret

    async def verify_token(self, token: str) -> Optional[UserAuthPayload]:
        if not self.jwt_secret:
            logger.error("[AUTH] Supabase JWT secret is missing from environment variables!")
            return None
            
        # Supabase provides secrets as Base64 strings. python-jose expects a raw byte string or
        # the literal base64 string if it matches the key length. To be safe, we attempt
        # to decode it if it looks like base64, otherwise we use it raw.
        secret = self.jwt_secret
        import base64
        try:
            # Check if it's base64 encoded by trying to decode it
            if len(secret) % 4 == 0 and not secret.startswith("sk-"):
                decoded_secret = base64.b64decode(secret)
                # Only use decoded if it actually changed and isn't garbage
                if decoded_secret != secret.encode():
                    secret = decoded_secret
        except Exception:
            pass

        secret_len = len(self.jwt_secret)
        try:
            # Inspect token header first
            try:
                unverified_header = jwt.get_unverified_header(token)
                alg = unverified_header.get("alg")
                if alg != "HS256":
                    return None
            except Exception:
                return None

            # Supabase uses HS256 algorithm.
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            
            # Hybrid check: Supabase uses 'sub', manual might use 'user_id'
            user_id = payload.get("sub") or payload.get("user_id")
            email = payload.get("email")
            role = payload.get("role")
            
            if not user_id or not email:
                logger.warning(f"[AUTH] Token payload missing identity fields. sub={user_id}, email={email}")
                return None
                
            # If a role is present in the token, it MUST be authenticated (Supabase).
            # Manual tokens created by Assest might omit the role field entirely.
            if role is not None and role != "authenticated":
                logger.warning(f"[AUTH] Token role is '{role}', expected 'authenticated'.")
                return None
                
            user_metadata = payload.get("user_metadata", {})
            full_name = user_metadata.get("full_name") or email.split("@")[0]
            
            return UserAuthPayload(
                user_id=user_id,
                email=email,
                full_name=full_name,
                metadata=payload
            )
        except JWTError as e:
            logger.error(f"[AUTH] Supabase JWT verification FAILED (Secret Length: {secret_len}). Error: {e}")
            return None
