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

# Supabase and OAuth providers removed. 
# Internal JWT verification is now handled directly in backend/api/users.py 
# using the app_secret_key.
