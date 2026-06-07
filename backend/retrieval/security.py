"""Security and permission filtering for retrieval results.

This module provides post-retrieval filtering to enforce workspace and
user-level access controls. For now it filters search results returned by
the vector store based on payload metadata fields: `is_public` and
`allowed_users`.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)



def apply_security_filter(
    results: List[Dict[str, Any]], 
    user_id: Optional[str], 
    is_development: bool,
    user_role: Optional[str] = "employee"
) -> List[Dict[str, Any]]:
    """Filter a list of result dicts based on access rules and user roles.

    - If is_development is False, permit items where is_public is True or
      allowed_users contains the user_id.
    - If user_role is 'guest' or 'employee', exclude items containing sensitive
      keywords (admin, credential, salary, financial) in their text, title, or path.
    """
    role = (user_role or "employee").lower()

    filtered = []
    for item in results:
        meta = item.get("metadata", {}) or {}
        
        # 1. User-level check (skip in dev to keep onboarding simple)
        if not is_development:
            is_public = meta.get("is_public")
            allowed = meta.get("allowed_users") or []
            if not is_public and (not user_id or user_id not in allowed):
                continue

        # 2. Role-based check (always checked to support testing)
        if role in ("guest", "employee"):
            text = str(item.get("text", "")).lower()
            title = str(meta.get("title", "")).lower()
            source_url = str(meta.get("source_url", "")).lower()
            
            import re
            sensitive_pattern = re.compile(
                r"\b(admin|credential|salary|financial|password|secret|payroll|compensation|revenue)\b"
            )
            if (
                sensitive_pattern.search(text)
                or sensitive_pattern.search(title)
                or sensitive_pattern.search(source_url)
            ):
                logger.info(f"Filtering out chunk {item.get('chunk_id')} due to sensitive keyword mapping to {role} role.")
                continue

        filtered.append(item)

    return filtered

