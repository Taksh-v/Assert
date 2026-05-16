import logging
import io
import asyncio
import hashlib
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from backend.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger(__name__)


class GoogleDriveConnector(BaseConnector):
    """
    Connector for Google Drive using the official API.
    Supports OAuth tokens and incremental sync via modifiedTime.
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
        return bool(
            config.get("access_token") or 
            config.get("service_account_info") or 
            config.get("credentials")
        )

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Connect using OAuth access_token or service account credentials."""
        from googleapiclient.discovery import build
        
        # Priority 1: OAuth access_token (from OAuth flow)
        if config.get("access_token"):
            from google.oauth2.credentials import Credentials
            
            creds = Credentials(
                token=config["access_token"],
                refresh_token=config.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.get("client_id"),
                client_secret=config.get("client_secret"),
            )
            service = build('drive', 'v3', credentials=creds)
            
            # Verify connection
            try:
                about = service.about().get(fields="user").execute()
                user_email = about.get("user", {}).get("emailAddress", "unknown")
                logger.info(f"Connected to Google Drive as: {user_email}")
                return service
            except Exception as e:
                logger.error(f"Google Drive connection verification failed: {e}")
                raise ConnectionError(f"Google Drive authentication failed: {e}")
        
        # Priority 2: Service account
        if config.get("service_account_info"):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_info(config["service_account_info"])
            service = build('drive', 'v3', credentials=creds)
            return service
        
        raise ConnectionError(
            "Google Drive connection requires an access_token (from OAuth) or service_account_info. "
            "Please connect via OAuth or provide credentials in the connector config."
        )

    async def fetch_documents(self, connection: Any, since: Optional[datetime] = None) -> Iterator[RawDocument]:
        """
        Fetch files modified since 'since'.
        """
        from googleapiclient.http import MediaIoBaseDownload

        logger.info(f"Fetching Google Drive documents updated since {since}...")
        
        query = "mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/pdf'"
        if since:
            query += f" and modifiedTime > '{since.isoformat()}Z'"
            
        next_page_token = None
        while True:
            response = await asyncio.to_thread(
                connection.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners, parents)',
                    pageToken=next_page_token
                ).execute
            )
            
            for file in response.get('files', []):
                file_id = file['id']
                mime_type = file['mimeType']
                
                try:
                    content = await self._download_content(connection, file_id, mime_type)
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    
                    yield RawDocument(
                        source_id=file_id,
                        source_type="google_drive",
                        workspace_id="default",
                        connector_id="gdrive-main",
                        title=file['name'],
                        raw_content=content,
                        source_url=file.get('webViewLink', ""),
                        content_hash=content_hash,
                        created_at=datetime.fromisoformat(file['createdTime'].replace("Z", "+00:00")),
                        modified_at=datetime.fromisoformat(file['modifiedTime'].replace("Z", "+00:00")),
                        breadcrumb=file.get('parents', []),
                        metadata=file
                    )
                except Exception as e:
                    logger.error(f"Error downloading file {file['name']}: {e}")
                    continue

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

    async def _download_content(self, service: Any, file_id: str, mime_type: str) -> str:
        """Download file content and convert to text elements."""
        from googleapiclient.http import MediaIoBaseDownload

        if mime_type == 'application/vnd.google-apps.document':
            # Export Google Doc as plain text
            return await asyncio.to_thread(
                service.files().export(fileId=file_id, mimeType='text/plain').execute
            )
        elif mime_type == 'application/pdf':
            # Download PDF bytes
            request = service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            while done is False:
                status, done = await asyncio.to_thread(downloader.next_chunk)
            
            # Parse with HybridParser
            elements = await self.parser.parse_bytes(file_io.getvalue(), f"{file_id}.pdf")
            return "\n\n".join([el["content"] for el in elements])
        else:
            # Try to export as plain text for other Google Workspace formats
            try:
                return await asyncio.to_thread(
                    service.files().export(fileId=file_id, mimeType='text/plain').execute
                )
            except Exception:
                return f"[Unsupported format: {mime_type}]"

    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """
        List all accessible files and folders for browsing.
        Paginates through all results for complete discovery.
        """
        logger.info("Listing Google Drive resources for discovery...")

        resources = []
        next_page_token = None
        
        while True:
            response = await asyncio.to_thread(
                connection.files().list(
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, iconLink, size, parents)",
                    orderBy="modifiedTime desc",
                    pageToken=next_page_token
                ).execute
            )
            
            for file in response.get('files', []):
                is_folder = file['mimeType'] == 'application/vnd.google-apps.folder'
                
                # Human-readable type
                type_map = {
                    'application/vnd.google-apps.document': 'Google Doc',
                    'application/vnd.google-apps.spreadsheet': 'Google Sheet',
                    'application/vnd.google-apps.presentation': 'Google Slides',
                    'application/vnd.google-apps.folder': 'Folder',
                    'application/pdf': 'PDF',
                }
                display_type = type_map.get(file['mimeType'], file['mimeType'].split('/')[-1])
                
                resources.append({
                    "id": file['id'],
                    "name": file['name'],
                    "type": "folder" if is_folder else "file",
                    "display_type": display_type,
                    "mime_type": file['mimeType'],
                    "last_modified": file.get('modifiedTime', ''),
                    "size": file.get('size'),
                    "icon": file.get('iconLink'),
                })
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            
            # Safety limit: don't fetch more than 1000 items in discovery
            if len(resources) >= 1000:
                break
        
        logger.info(f"Discovered {len(resources)} Google Drive resources")
        return resources
