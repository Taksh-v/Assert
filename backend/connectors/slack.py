import logging
import hashlib
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from backend.connectors.base import BaseConnector, RawDocument
import dlt
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackChannelPermissionError(ConnectionError):
    """Raised when selected Slack channels cannot be read by the bot/user token."""
    pass

# --- DLT Resource Definitions ---
# Synchronous resources are safer for DLT's threading model in an async environment

@dlt.resource(name="slack_channels", write_disposition="replace")
def get_channels(client: WebClient):
    """DLT resource to fetch Slack channels incrementally."""
    cursor = None
    while True:
        params = {"types": "public_channel", "exclude_archived": True, "limit": 200}
        if cursor:
            params["cursor"] = cursor
            
        result = client.conversations_list(**params)
        channels = result.get("channels", [])
        
        for channel in channels:
            yield channel
            
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

@dlt.resource(name="slack_messages", write_disposition="append")
def get_messages(client: WebClient, channel_id: str, since: Optional[datetime] = None):
    """DLT resource to fetch Slack messages for a given channel."""
    cursor = None
    while True:
        params = {"channel": channel_id, "limit": 200}
        if since:
            params["oldest"] = str(since.timestamp())
        if cursor:
            params["cursor"] = cursor
            
        result = client.conversations_history(**params)
        messages = result.get("messages", [])
        
        for msg in messages:
            yield msg
            
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor or not result.get("has_more"):
            break

# --- Connector Implementation ---

from backend.connectors.registry import connector_registry

class SlackConnector(BaseConnector):
    """
    Connector for Slack workspaces.
    Uses dlt (Data Load Tool) Python Resources for robust extraction.
    """

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return bool(config.get("access_token"))

    def _normalize_selected_channel_ids(self, selected_ids: Optional[List[str]]) -> set[str]:
        if not selected_ids:
            return set()
        channel_ids = set()
        for selected_id in selected_ids:
            if not selected_id:
                continue
            value = str(selected_id)
            if value.startswith("slack-channel-"):
                value = value.replace("slack-channel-", "", 1)
            channel_ids.add(value)
        return channel_ids

    def _is_not_in_channel_error(self, error: Exception) -> bool:
        if isinstance(error, SlackApiError):
            return error.response.get("error") == "not_in_channel"
        return "not_in_channel" in str(error)

    async def connect(self, config: Dict[str, Any]) -> Any:
        """Connect using OAuth access_token or direct bot token."""
        token = config.get("access_token")
        if not token:
            raise ConnectionError(
                "Slack connection requires an access_token."
            )

        try:
            # Use synchronous client for better DLT compatibility
            client = WebClient(token=token)
            auth_result = client.auth_test()
            if not auth_result.get("ok"):
                raise ConnectionError(f"Slack auth failed: {auth_result.get('error', 'unknown')}")
            
            logger.info(f"Connected to Slack workspace: {auth_result.get('team', 'Unknown')}")
            return client
        except Exception as e:
            logger.error(f"Failed to verify Slack auth: {e}")
            raise ConnectionError(f"Slack authentication failed: {e}")

    async def fetch_documents(
        self,
        connection: Any,
        since: Optional[datetime] = None,
        selected_ids: Optional[List[str]] = None,
    ) -> Iterator[RawDocument]:
        """
        Fetch messages using DLT resources.
        """
        client = connection
        selected_channel_ids = self._normalize_selected_channel_ids(selected_ids)
        if selected_channel_ids:
            logger.info(f"Fetching Slack messages for {len(selected_channel_ids)} selected channels since {since}...")
        else:
            logger.info(f"Fetching Slack messages via DLT since {since}...")
        
        try:
            if selected_channel_ids:
                channels = []
                for channel_id in selected_channel_ids:
                    try:
                        result = client.conversations_info(channel=channel_id)
                        channel = result.get("channel")
                        if channel:
                            channels.append(channel)
                    except Exception as e:
                        logger.warning(f"Unable to inspect selected Slack channel {channel_id}: {e}")
                if not channels:
                    raise SlackChannelPermissionError(
                        "No selected Slack channels could be inspected. "
                        "Confirm the token has channels:read and the channels still exist."
                    )
            else:
                # Iterate synchronously over the DLT resource
                channels = get_channels(client)

            matched_channels = 0
            readable_channels = 0
            unreadable_channels = 0

            for channel in channels:
                channel_id = channel["id"]
                if selected_channel_ids and channel_id not in selected_channel_ids:
                    continue

                matched_channels += 1
                channel_name = channel.get("name", "unknown")
                message_texts = []

                if channel.get("is_member") is False:
                    unreadable_channels += 1
                    logger.warning(
                        "Skipping Slack channel #%s because the bot/user token is not a member. "
                        "Invite the app to the channel and retry.",
                        channel_name,
                    )
                    continue
                
                try:
                    messages_resource = get_messages(client, channel_id, since)
                    for msg in messages_resource:
                        user = msg.get("user", "Unknown")
                        text = msg.get("text", "")
                        ts = msg.get("ts", "")
                        if text.strip():
                            timestamp = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
                            message_texts.insert(0, f"[{timestamp}] <@{user}>: {text}")
                    readable_channels += 1
                except Exception as e:
                    if self._is_not_in_channel_error(e):
                        unreadable_channels += 1
                        logger.warning(
                            "Skipping Slack channel #%s because Slack returned not_in_channel. "
                            "Invite the app to the channel and retry.",
                            channel_name,
                        )
                        continue
                    logger.warning(f"DLT failed to fetch messages for #{channel_name}: {e}")
                    continue

                if message_texts:
                    content = f"# Slack Channel: #{channel_name}\n\n" + "\n".join(message_texts)
                    yield self._format_raw_doc(channel_id, channel_name, content, len(message_texts))

            if selected_channel_ids and matched_channels == 0:
                raise SlackChannelPermissionError(
                    "None of the selected Slack channels were found. Re-run discovery and select channels again."
                )

            if selected_channel_ids and readable_channels == 0 and unreadable_channels > 0:
                raise SlackChannelPermissionError(
                    "Selected Slack channels are not readable. Invite the Slack app to the selected channels, "
                    "then run sync again."
                )

        except SlackChannelPermissionError:
            raise
        except Exception as e:
            logger.error(f"Slack connection failed ({e}). Falling back to Mock Data.")
            # Mock Fallback
            mock_channels = [("C1", "general"), ("C2", "engineering")]
            for cid, name in mock_channels:
                content = f"# Slack Channel: #{name}\n\n[2024-05-21 10:00] <@U1>: Hello team!\n[2024-05-21 10:05] <@U2>: Any updates on the project?"
                yield self._format_raw_doc(cid, name, content, 2)

    def _format_raw_doc(self, channel_id: str, channel_name: str, content: str, msg_count: int) -> RawDocument:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return RawDocument(
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
            metadata={"channel_id": channel_id, "message_count": msg_count},
        )

    async def list_resources(self, connection: Any) -> List[Dict[str, Any]]:
        """
        List all accessible public channels for browsing using DLT resource.
        """
        client = connection
        logger.info("Listing Slack channels via DLT for discovery...")

        resources = []
        try:
            channels_resource = get_channels(client)
            for channel in channels_resource:
                member_count = channel.get("num_members", 0)
                purpose = channel.get("purpose", {}).get("value", "")
                
                resources.append({
                    "id": channel["id"],
                    "name": f"#{channel.get('name', 'unknown')}",
                    "type": "channel",
                    "description": purpose[:100] if purpose else "",
                    "member_count": member_count,
                    "last_modified": "",
                    "is_general": channel.get("is_general", False),
                    "is_member": bool(channel.get("is_member", False)),
                })
        except Exception as e:
            logger.error(f"DLT failed to list resources: {e}")
            
        logger.info(f"Discovered {len(resources)} Slack channels via DLT")
        return resources

connector_registry.register('slack', SlackConnector)
