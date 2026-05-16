import logging
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from backend.core.config import get_settings
from backend.query.retriever import Retriever
from backend.query.generator import Generator

settings = get_settings()
logger = logging.getLogger(__name__)

class AssestSlackBot:
    """
    Slack Bot for Assest Company Brain.
    Uses Async Socket Mode for real-time interaction.
    """

    def __init__(self):
        self.app = AsyncApp(token=settings.slack_bot_token)
        self.retriever = Retriever()
        self.generator = Generator()
        self._register_handlers()

    def _register_handlers(self):
        """Register Slack event handlers."""
        
        @self.app.event("app_mention")
        async def handle_app_mentions(event, say):
            """Handle direct mentions in channels."""
            await self._process_message(event, say)

        @self.app.message("")
        async def handle_direct_messages(event, say):
            """Handle DMs."""
            if event.get("channel_type") == "im":
                await self._process_message(event, say)

    async def _process_message(self, event, say):
        """Process incoming message, retrieve knowledge, and generate answer."""
        text = event.get("text")
        user = event.get("user")
        channel = event.get("channel")
        
        logger.info(f"Received message from user {user} in channel {channel}: {text}")
        
        # 1. Retrieve knowledge
        # In a real app, workspace_id would be mapped from the Slack team_id
        workspace_id = "default-workspace" 
        
        try:
            # Retrieve
            context_results = await self.retriever.search(text, workspace_id)
            # Generate
            answer = await self.generator.generate_answer(text, context_results)
            
            # Format sources for Slack
            sources_text = ""
            if context_results:
                sources_text = "\n\n*Sources:*\n" + "\n".join([f"• <{r.source_url}|{r.title}>" for r in context_results])
            
            # Send reply
            await say(f"<@{user}> {answer.answer_text}{sources_text}")
            
        except Exception as e:
            logger.error(f"Error processing Slack message: {e}")
            await say(f"Sorry <@{user}>, I encountered an error while consulting the brain.")

    async def start(self):
        """Start the Slack bot in Socket Mode."""
        if not settings.slack_app_token or not settings.slack_bot_token:
            logger.warning("Slack tokens not configured. Skipping bot startup.")
            return

        logger.info("Starting Assest Slack Bot in Async Socket Mode...")
        handler = AsyncSocketModeHandler(self.app, settings.slack_app_token)
        await handler.start_async()
