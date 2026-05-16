import logging
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import hashlib
from notion_client import AsyncClient
from backend.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger(__name__)


class NotionConnector(BaseConnector):
    """
    Connector for Notion workspaces using the official notion-client.
    Supports OAuth tokens and incremental sync via last_edited_time.
    """

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return bool(config.get("access_token") or config.get("notion_token") or config.get("api_key"))

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Connect using OAuth access_token or direct API key."""
        # Priority: OAuth access_token > direct notion_token > api_key
        token = config.get("access_token") or config.get("notion_token") or config.get("api_key")
        
        if not token:
            raise ConnectionError(
                "Notion connection requires an access_token (from OAuth) or api_key. "
                "Please connect via OAuth or provide a token in the connector config."
            )

        client = AsyncClient(auth=token)
        # Verify connection with a lightweight API call
        try:
            user_info = await client.users.me()
            logger.info(f"Connected to Notion as: {user_info.get('name', 'Unknown')}")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Notion: {e}")
            raise ConnectionError(f"Notion authentication failed: {e}")

    async def fetch_documents(self, connection: AsyncClient, since: Optional[datetime] = None) -> Iterator[RawDocument]:
        """
        Fetch all pages updated since 'since'.
        """
        logger.info(f"Fetching Notion documents updated since {since}...")
        
        has_more = True
        next_cursor = None
        
        while has_more:
            # Search across all pages/databases
            params = {
                "page_size": 100,
                "start_cursor": next_cursor
            }
            
            # Filter to both pages and databases
            params["filter"] = {
                "value": "page", # Notion search filter 'value' can be 'page' or 'database'
                "property": "object"
            }
            # Note: Notion search filter is 'or', but 'search' actually returns both if filter is omitted.
            # To be safe and fetch everything the user might have selected, we remove the strict 'page' filter.
            del params["filter"] 
            
            response = await connection.search(**params)
            
            for result in response.get("results", []):
                res_type = result["object"]
                if res_type not in ["page", "database"]:
                    continue
                
                # Double check modified time (search filter is sometimes loose)
                last_edited = datetime.fromisoformat(result["last_edited_time"].replace("Z", "+00:00"))
                if since and last_edited.replace(tzinfo=None) <= since.replace(tzinfo=None):
                    continue

                # Fetch content
                page_id = result["id"]
                if res_type == "page":
                    title = self._extract_title(result)
                    content = await self._fetch_page_content(connection, page_id)
                else:
                    # For databases, we'll index the title and metadata for now
                    title_arr = result.get("title", [])
                    title = "".join([t.get("plain_text", "") for t in title_arr]) if title_arr else "Untitled Database"
                    content = f"Notion Database: {title}\nURL: {result.get('url', '')}"
                
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                
                yield RawDocument(
                    source_id=page_id,
                    source_type="notion",
                    workspace_id="default", 
                    connector_id="notion-main",
                    title=title,
                    raw_content=content,
                    content_format="html",
                    source_url=result.get("url", ""),
                    content_hash=content_hash,
                    created_at=datetime.fromisoformat(result["created_time"].replace("Z", "+00:00")),
                    modified_at=last_edited,
                    breadcrumb=self._extract_breadcrumb(result),
                    metadata=result
                )
            
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")

    def _extract_title(self, page: Dict[str, Any]) -> str:
        properties = page.get("properties", {})
        for name, prop in properties.items():
            if prop["type"] == "title":
                return "".join([t["plain_text"] for t in prop["title"]]) if prop["title"] else "Untitled"
        return "Untitled"

    async def _fetch_page_content(self, client: AsyncClient, page_id: str) -> str:
        """Fetch all blocks for a page and join as structured HTML text."""
        blocks = []
        has_more = True
        next_cursor = None
        
        while has_more:
            response = await client.blocks.children.list(block_id=page_id, start_cursor=next_cursor)
            blocks.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")
            
        content_parts = []
        for block in blocks:
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

    async def list_resources(self, connection: AsyncClient) -> List[Dict[str, Any]]:
        """
        List all accessible pages and databases for browsing.
        Paginates through all results for complete discovery.
        """
        logger.info("Listing Notion resources for discovery...")

        resources = []
        has_more = True
        next_cursor = None
        
        while has_more:
            params = {"page_size": 100}
            if next_cursor:
                params["start_cursor"] = next_cursor
                
            response = await connection.search(**params)
            
            for result in response.get("results", []):
                res_type = result["object"]
                
                if res_type == "page":
                    title = self._extract_title(result)
                elif res_type == "database":
                    title_arr = result.get("title", [])
                    title = "".join([t.get("plain_text", "") for t in title_arr]) if title_arr else "Untitled Database"
                else:
                    continue
                
                # Extract icon
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
            
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")
            
            # Safety limit: don't fetch more than 1000 items in discovery
            if len(resources) >= 1000:
                break
        
        logger.info(f"Discovered {len(resources)} Notion resources")
        return resources

    def _extract_breadcrumb(self, result: Dict[str, Any]) -> List[str]:
        # Notion parent objects can be workspace, page, or database
        parent = result.get("parent", {})
        if parent.get("type") == "workspace":
            return ["Workspace"]
        elif parent.get("type") == "page_id":
            return ["Workspace", f"Page:{parent['page_id'][:8]}"]
        elif parent.get("type") == "database_id":
            return ["Workspace", f"Database:{parent['database_id'][:8]}"]
        return []
