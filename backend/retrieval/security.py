"""Security and permission filtering for retrieval results.

This module provides post-retrieval filtering to enforce workspace and
user-level access controls. For now it filters search results returned by
the vector store based on payload metadata fields: `is_public` and
`allowed_users`.
"""
from typing import List, Dict, Any, Optional


def apply_security_filter(results: List[Dict[str, Any]], user_id: Optional[str], is_development: bool) -> List[Dict[str, Any]]:
    """Filter a list of result dicts based on access rules.

    - If `is_development` is True, return results unchanged to keep dev experience.
    - If `user_id` is provided, permit items where `is_public` is True or
      `allowed_users` contains the user_id.
    - Otherwise, only permit items marked `is_public`.
    """
    if is_development:
        return results

    filtered = []
    for item in results:
        meta = item.get("metadata", {}) or {}
        if meta.get("is_public"):
            filtered.append(item)
            continue
        allowed = meta.get("allowed_users") or []
        if user_id and user_id in allowed:
            filtered.append(item)
            continue

    return filtered
