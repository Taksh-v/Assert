import os
import logging
import hashlib
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from backend.connectors.base import BaseConnector, RawDocument
from backend.connectors.registry import connector_registry

logger = logging.getLogger(__name__)

class FileUploadConnector(BaseConnector):
    """
    Connector for manually uploaded local files.
    Files are stored in a local directory per connector.
    """

    def __init__(self):
        self._parser = None

    @property
    def parser(self):
        """Lazy-init parser to avoid import-time overhead."""
        if self._parser is None:
            from backend.ingestion.document_parser import HybridParser
            self._parser = HybridParser()
        return self._parser

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return True

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Return the upload directory path."""
        upload_dir = config.get("upload_dir")
        if not upload_dir:
            raise ConnectionError("File upload connector configuration missing 'upload_dir'")
        os.makedirs(upload_dir, exist_ok=True)
        return upload_dir

    async def fetch_documents(
        self,
        connection: Any,
        since: Optional[datetime] = None,
        selected_ids: Optional[List[str]] = None,
    ) -> Iterator[RawDocument]:
        """
        Fetch local files from the upload directory.
        """
        upload_dir = connection
        logger.info(f"Scanning local files in {upload_dir}...")
        
        if not os.path.exists(upload_dir):
            return

        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            if not os.path.isfile(file_path):
                continue

            if selected_ids and filename not in selected_ids:
                continue

            # Read and parse file
            try:
                stat = os.stat(file_path)
                mtime = datetime.fromtimestamp(stat.st_mtime)
                
                # Check since filter
                if since and mtime <= since:
                    continue

                # Read bytes for hash and parsing
                with open(file_path, "rb") as f:
                    file_bytes = f.read()

                content_hash = hashlib.sha256(file_bytes).hexdigest()

                # Parse file content
                ext = filename.lower().split('.')[-1]
                if ext in ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'html', 'htm', 'mp3', 'mp4', 'wav', 'm4a']:
                    elements = await self.parser.parse(file_path)
                    content = "\n\n".join([el["content"] for el in elements])
                else:
                    content = file_bytes.decode('utf-8', errors='ignore')

                yield RawDocument(
                    source_id=filename,
                    source_type="file_upload",
                    workspace_id="default",  # Will be overridden by pipeline
                    connector_id="file_upload",  # Will be overridden by pipeline
                    title=filename,
                    raw_content=content,
                    source_url=file_path,
                    content_hash=content_hash,
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                    modified_at=mtime,
                    breadcrumb=[],
                    metadata={
                        "filename": filename,
                        "file_size": stat.st_size,
                        "extension": ext
                    }
                )
            except Exception as e:
                logger.error(f"Error reading/parsing local file {filename}: {e}")
                continue

    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """List uploaded files."""
        upload_dir = connection
        if not os.path.exists(upload_dir):
            return []

        resources = []
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                ext = filename.split('.')[-1].upper()
                resources.append({
                    "id": filename,
                    "name": filename,
                    "type": "file",
                    "display_type": ext,
                    "mime_type": f"application/{ext.lower()}",
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size": stat.st_size,
                })
        return resources

connector_registry.register('file_upload', FileUploadConnector)
