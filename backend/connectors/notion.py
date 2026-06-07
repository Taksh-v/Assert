import logging
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import hashlib
import dlt
from notion_client import Client
from backend.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger(__name__)

# --- DLT Resource Definitions ---

@dlt.resource(name="notion_pages", write_disposition="replace")
def get_pages(client: Client, since: Optional[datetime] = None):
    """DLT resource to fetch Notion pages/databases incrementally."""
    next_cursor = None
    has_more = True
    
    while has_more:
        params = {"page_size": 100}
        if next_cursor:
            params["start_cursor"] = next_cursor
            
        response = client.search(**params)
        
        for result in response.get("results", []):
            res_type = result["object"]
            if res_type not in ["page", "database"]:
                continue
                
            last_edited = datetime.fromisoformat(result["last_edited_time"].replace("Z", "+00:00"))
            if since and last_edited.replace(tzinfo=None) <= since.replace(tzinfo=None):
                continue
                
            yield result
            
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

@dlt.resource(name="notion_blocks", write_disposition="append")
def get_blocks(client: Client, page_id: str):
    """DLT resource to fetch content blocks for a Notion page."""
    has_more = True
    next_cursor = None
    
    while has_more:
        response = client.blocks.children.list(block_id=page_id, start_cursor=next_cursor)
        for block in response.get("results", []):
            yield block
            
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")


# --- Connector Implementation ---

from backend.connectors.registry import connector_registry

class NotionConnector(BaseConnector):
    """
    Connector for Notion workspaces.
    Uses dlt (Data Load Tool) Python Resources for robust extraction.
    Supports OAuth tokens and incremental sync via last_edited_time.
    """

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return bool(config.get("access_token") or config.get("notion_token") or config.get("api_key"))

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Connect using OAuth access_token or direct API key."""
        token = config.get("access_token") or config.get("notion_token") or config.get("api_key")
        if not token:
            raise ConnectionError(
                "Notion connection requires an access_token (from OAuth) or api_key. "
                "Please connect via OAuth or provide a token in the connector config."
            )

        # Use synchronous client
        client = Client(auth=token)
        try:
            user_info = client.users.me()
            logger.info(f"Connected to Notion via DLT as: {user_info.get('name', 'Unknown')}")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Notion: {e}")
            raise ConnectionError(f"Notion authentication failed: {e}")

    async def fetch_documents(
        self,
        connection: Any,
        since: Optional[datetime] = None,
        selected_ids: Optional[List[str]] = None,
    ) -> Iterator[RawDocument]:
        """
        Fetch all pages updated since 'since' using DLT extraction with mock fallback.
        """
        client = connection
        logger.info(f"Fetching Notion documents via DLT since {since}...")
        
        try:
            # Iterate synchronously over the DLT resource (dlt handles the generator)
            pages_resource = get_pages(client, since)
            for result in pages_resource:
                res_type = result["object"]
                page_id = result["id"]
                if selected_ids and page_id not in selected_ids:
                    continue
                last_edited = datetime.fromisoformat(result["last_edited_time"].replace("Z", "+00:00"))
                
                if res_type == "page":
                    title = self._extract_title(result)
                    content = self._build_page_content_via_dlt(client, page_id)
                else:
                    title_arr = result.get("title", [])
                    title = "".join([t.get("plain_text", "") for t in title_arr]) if title_arr else "Untitled Database"
                    content = f"Notion Database: {title}\nURL: {result.get('url', '')}"
                
                yield self._format_raw_doc(page_id, title, content, result, last_edited)
        except Exception as e:
            logger.error(f"Notion connection failed: {e}")
            raise ConnectionError(f"Notion sync failed: {str(e)}") from e

    def _format_raw_doc(self, page_id: str, title: str, content: str, raw_metadata: Dict, modified_at: datetime) -> RawDocument:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return RawDocument(
            source_id=page_id,
            source_type="notion",
            workspace_id="default", 
            connector_id="notion-main",
            title=title,
            raw_content=content,
            content_format="html",
            source_url=raw_metadata.get("url", ""),
            content_hash=content_hash,
            created_at=datetime.utcnow(),
            modified_at=modified_at,
            breadcrumb=self._extract_breadcrumb(raw_metadata),
            metadata=raw_metadata
        )

    def _build_page_content_via_dlt(self, client: Client, page_id: str) -> str:
        """Helper to fetch and format blocks using DLT resource."""
        blocks_resource = get_blocks(client, page_id)
        content_parts = []
        
        for block in blocks_resource:
            b_type = block["type"]
            tag_map = {
                "paragraph": "p",
                "heading_1": "h1",
                "heading_2": "h2",
                "heading_3": "h3",
                "bulleted_list_item": "li",
                "numbered_list_item": "li",
                "code": "code",
                "to_do": "li",
                "toggle": "details",
                "quote": "blockquote",
                "callout": "div",
            }
            
            if b_type in tag_map:
                tag = tag_map[b_type]
                rich_text = block[b_type].get("rich_text", [])
                text = "".join([t["plain_text"] for t in rich_text])
                if text.strip():
                    content_parts.append(f"<{tag}>{text}</{tag}>")
            elif b_type == "table":
                content_parts.append("<table>[Complex Table Placeholder]</table>")
            elif b_type == "divider":
                content_parts.append("<hr/>")
            elif b_type == "image":
                img_data = block.get("image", {})
                url = img_data.get("file", img_data.get("external", {})).get("url", "")
                content_parts.append(f'<img src="{url}" alt="image"/>')
                
        return "\n".join(content_parts)

    def _extract_title(self, page: Dict[str, Any]) -> str:
        properties = page.get("properties", {})
        for name, prop in properties.items():
            if prop["type"] == "title":
                return "".join([t["plain_text"] for t in prop["title"]]) if prop["title"] else "Untitled"
        return "Untitled"

    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """
        List all accessible pages and databases for browsing using DLT.
        """
        client = connection
        logger.info("Listing Notion resources via DLT for discovery...")

        resources = []
        try:
            pages_resource = get_pages(client, None)
            for result in pages_resource:
                res_type = result["object"]
                if res_type == "page":
                    title = self._extract_title(result)
                elif res_type == "database":
                    title_arr = result.get("title", [])
                    title = "".join([t.get("plain_text", "") for t in title_arr]) if title_arr else "Untitled Database"
                else:
                    continue
                
                icon_data = result.get("icon")
                icon = None
                if icon_data:
                    if icon_data.get("type") == "emoji":
                        icon = icon_data.get("emoji")
                    elif icon_data.get("type") == "external":
                        icon = icon_data.get("external", {}).get("url")
                
                resources.append({
                    "id": result["id"],
                    "name": title,
                    "type": res_type,
                    "icon": icon,
                    "last_modified": result.get("last_edited_time", ""),
                    "url": result.get("url", ""),
                })
                
                if len(resources) >= 1000:
                    break
        except Exception as e:
            logger.error(f"DLT failed to list resources: {e}")
                
        logger.info(f"Discovered {len(resources)} Notion resources via DLT")
        return resources

    def _extract_breadcrumb(self, result: Dict[str, Any]) -> List[str]:
        parent = result.get("parent", {})
        if parent.get("type") == "workspace":
            return ["Workspace"]
        elif parent.get("type") == "page_id":
            return ["Workspace", f"Page:{parent['page_id'][:8]}"]
        elif parent.get("type") == "database_id":
            return ["Workspace", f"Database:{parent['database_id'][:8]}"]
        return []

connector_registry.register('notion', NotionConnector)
