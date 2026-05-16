import logging
import hashlib
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from backend.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """
    Connector for Slack workspaces.
    Uses slack_sdk.WebClient with OAuth or bot tokens.
    Fetches messages from selected channels as knowledge documents.
    """

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return bool(config.get("access_token"))

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Connect using OAuth access_token or direct bot token."""
        token = config.get("access_token")
        
        if not token:
            raise ConnectionError(
                "Slack connection requires an access_token (from OAuth or bot token). "
                "Please connect via OAuth or set slack_bot_token in .env."
            )

        try:
            from slack_sdk.web.async_client import AsyncWebClient
            client = AsyncWebClient(token=token)
            
            # Verify connection
            auth_result = await client.auth_test()
            if not auth_result.get("ok"):
                raise ConnectionError(f"Slack auth failed: {auth_result.get('error', 'unknown')}")
            
            logger.info(f"Connected to Slack workspace: {auth_result.get('team', 'Unknown')}")
            return client
        except ImportError:
            raise ConnectionError("slack_sdk is not installed. Run: pip install slack_sdk")
        except Exception as e:
            logger.error(f"Failed to connect to Slack: {e}")
            raise ConnectionError(f"Slack authentication failed: {e}")

    async def fetch_documents(self, connection: Any, since: Optional[datetime] = None) -> Iterator[RawDocument]:
        """
        Fetch messages from all accessible public channels.
        Groups messages by channel into single documents.
        """
        logger.info(f"Fetching Slack messages since {since}...")
        
        # Get list of channels
        channels_result = await connection.conversations_list(
            types="public_channel",
            limit=200,
            exclude_archived=True
        )
        
        channels = channels_result.get("channels", [])
        
        for channel in channels:
            channel_id = channel["id"]
            channel_name = channel["name"]
            
            try:
                # Fetch messages from channel
                params = {
                    "channel": channel_id,
                    "limit": 200,
                }
                if since:
                    params["oldest"] = str(since.timestamp())
                
                history_result = await connection.conversations_history(**params)
                messages = history_result.get("messages", [])
                
                if not messages:
                    continue
                
                # Combine messages into a single document per channel
                message_texts = []
                for msg in reversed(messages):  # Oldest first
                    user = msg.get("user", "Unknown")
                    text = msg.get("text", "")
                    ts = msg.get("ts", "")
                    if text.strip():
                        timestamp = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
                        message_texts.append(f"[{timestamp}] <@{user}>: {text}")
                
                if not message_texts:
                    continue
                    
                content = f"# Slack Channel: #{channel_name}\n\n" + "\n".join(message_texts)
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                
                yield RawDocument(
                    source_id=f"slack-channel-{channel_id}",
                    source_type="slack",
                    workspace_id="default",
                    connector_id="slack-main",
                    title=f"#{channel_name}",
                    raw_content=content,
                    content_format="plain_text",
                    source_url=f"https://slack.com/app_redirect?channel={channel_id}",
                    content_hash=content_hash,
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow(),
                    breadcrumb=["Slack", channel_name],
                    metadata={"channel_id": channel_id, "message_count": len(messages)},
                )
            except Exception as e:
                logger.warning(f"Failed to fetch messages from #{channel_name}: {e}")
                continue

    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """
        List all accessible public channels for browsing.
        """
        logger.info("Listing Slack channels for discovery...")
        
        resources = []
        cursor = None
        
        while True:
            params = {
                "types": "public_channel",
                "limit": 200,
                "exclude_archived": True,
            }
            if cursor:
                params["cursor"] = cursor
            
            result = await connection.conversations_list(**params)
            channels = result.get("channels", [])
            
            for channel in channels:
                member_count = channel.get("num_members", 0)
                purpose = channel.get("purpose", {}).get("value", "")
                
                resources.append({
                    "id": channel["id"],
                    "name": f"#{channel['name']}",
                    "type": "channel",
                    "description": purpose[:100] if purpose else "",
                    "member_count": member_count,
                    "last_modified": "",  # Slack doesn't expose this for channels
                    "is_general": channel.get("is_general", False),
                })
            
            # Pagination
            response_metadata = result.get("response_metadata", {})
            cursor = response_metadata.get("next_cursor")
            if not cursor:
                break
        
        logger.info(f"Discovered {len(resources)} Slack channels")
        return resources
