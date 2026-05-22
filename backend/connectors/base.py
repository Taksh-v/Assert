from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel


class RawDocument(BaseModel):
    """Standard format for raw documents fetched from any source."""
    source_id: str
    source_type: str
    workspace_id: str
    connector_id: str
    
    title: str
    raw_content: str
    content_format: str = "plain_text"
    
    source_url: str
    author_id: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    
    # Enrichment (Blueprint Layer 2 & 5)
    breadcrumb: List[str] = [] # Folder path or nesting
    permissions: Dict[str, Any] = {} # ACLs from source
    metadata: Dict[str, Any] = {} # Raw metadata from source
    
    content_hash: str
    fetched_at: datetime = datetime.utcnow()


class BaseConnector(ABC):
    """
    Abstract base class for all data source connectors.
    """

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Verify the configuration is structurally valid."""
        pass

    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> Any:
        """Establish and verify the connection using OAuth tokens or API keys."""
        pass

    @abstractmethod
    async def fetch_documents(
        self,
        connection: Any,
        since: Optional[datetime] = None,
        selected_ids: Optional[List[str]] = None,
    ) -> Iterator[RawDocument]:
        """Fetch documents from the source."""
        pass

    @abstractmethod
    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """List available resources (pages, files, channels) for discovery browsing."""
        pass

    async def disconnect(self, connection: Any) -> None:
        """Optional cleanup when disconnecting a connector."""
        pass
