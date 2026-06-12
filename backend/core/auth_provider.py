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
            logger.error("Supabase JWT secret is not configured.")
            return None
        try:
            # Supabase uses HS256 algorithm.
            # We skip verify_aud by default because Supabase tokens can have varying audiences,
            # but we explicitly verify the user's role is authenticated.
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            
            user_id = payload.get("sub")
            email = payload.get("email")
            role = payload.get("role")
            
            if not user_id or not email:
                logger.warning("Supabase token payload is missing 'sub' or 'email'.")
                return None
                
            if role != "authenticated":
                logger.warning(f"Supabase token role is '{role}', expected 'authenticated'.")
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
            logger.warning(f"Failed to decode Supabase token: {e}")
            return None
