import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

class UnifiedDocument(BaseModel):
    """
    Blueprint Layer 2: Unified Internal Schema.
    Ensures consistency across all data sources.
    """
    source_id: str = Field(..., description="External ID from the source system")
    workspace_id: str = Field(..., description="Internal workspace identifier")
    document_id: str = Field(..., description="Unique internal document identifier")
    document_type: str = Field(default="general", description="Normalized document type (sop, policy, code, etc.)")
    mime_type: str = Field(default="text/plain", description="Source file MIME type")
    title: str = Field(..., description="Document title")
    raw_content: str = Field(..., description="Cleaned, normalized text content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")
    permissions: List[str] = Field(default_factory=list, description="ACLs and access permissions")
    source_url: str = Field(..., description="Direct link to source")
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentNormalizer:
    """
    Converts source-specific data into the Unified Internal Schema.
    """
    
    def normalize_notion(self, page_data: Dict[str, Any], workspace_id: str) -> UnifiedDocument:
        """Normalize a Notion page."""
        return UnifiedDocument(
            source_id=page_data.get("id", ""),
            workspace_id=workspace_id,
            document_id=f"notion_{page_data.get('id')}",
            document_type="wiki_page",
            mime_type="application/vnd.notion.page",
            title=page_data.get("title", "Untitled Notion Page"),
            raw_content=page_data.get("content", ""),
            source_url=page_data.get("url", ""),
            metadata={
                "last_edited_by": page_data.get("last_edited_by"),
                "parent_id": page_data.get("parent_id")
            },
            permissions=page_data.get("permissions", ["public"]) # Default to public for now
        )

    def normalize_slack(self, message_data: Dict[str, Any], workspace_id: str) -> UnifiedDocument:
        """Normalize a Slack message/thread."""
        return UnifiedDocument(
            source_id=message_data.get("ts", ""),
            workspace_id=workspace_id,
            document_id=f"slack_{message_data.get('ts')}",
            document_type="conversation",
            mime_type="application/vnd.slack.message",
            title=f"Slack Thread: {message_data.get('ts')}",
            raw_content=message_data.get("text", ""),
            source_url=message_data.get("url", ""),
            metadata={
                "channel_id": message_data.get("channel"),
                "user_id": message_data.get("user")
            },
            permissions=message_data.get("permissions", ["member"])
        )

    def normalize_generic(self, raw_data: Dict[str, Any], workspace_id: str) -> UnifiedDocument:
        """Fall-back normalization for other sources."""
        return UnifiedDocument(
            source_id=raw_data.get("source_id", "unknown"),
            workspace_id=workspace_id,
            document_id=raw_data.get("document_id", "unknown"),
            title=raw_data.get("title", "Untitled"),
            raw_content=raw_data.get("content", ""),
            source_url=raw_data.get("source_url", ""),
            metadata=raw_data.get("metadata", {}),
            permissions=raw_data.get("permissions", [])
        )
