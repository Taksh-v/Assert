import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.core.database import async_session, upsert_idempotent
from sqlalchemy import Column, String, Text, DateTime, JSON
from backend.core.database import Base

logger = logging.getLogger(__name__)


class UserMemory(Base):
    """
    Blueprint Layer 16: Agentic Memory Layer.
    Stores episodic (conversation history) and semantic (user preferences) memory.
    """
    __tablename__ = "user_memories"

    id = Column(String, primary_key=True) # Usually user_id
    workspace_id = Column(String, nullable=False)
    
    # Semantic Memory: What the user likes, their role, etc.
    preferences = Column(JSON, default={})
    
    # Episodic Memory: Summary of recent interactions
    recent_context_summary = Column(Text, nullable=True)
    
    last_updated_at = Column(DateTime, default=datetime.utcnow)


class MemoryManager:
    """
    Manages user-specific context and preferences across sessions.
    """

    async def get_memory(self, user_id: str, workspace_id: str) -> Optional[UserMemory]:
        async with async_session() as session:
            from sqlalchemy import select
            stmt = select(UserMemory).where(
                UserMemory.id == user_id,
                UserMemory.workspace_id == workspace_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def update_preferences(self, user_id: str, workspace_id: str, new_prefs: Dict[str, Any]):
        """Update long-term semantic memory."""
        async with async_session() as session:
            await upsert_idempotent(
                session,
                UserMemory,
                lookup_fields={"id": user_id, "workspace_id": workspace_id},
                update_fields={"preferences": new_prefs, "last_updated_at": datetime.utcnow()}
            )

    async def summarize_episode(self, user_id: str, workspace_id: str, new_interaction: str):
        """
        Update episodic memory with an incremental summary using the local brain.
        """
        from backend.core.llm_client import LLMClient
        llm = LLMClient(model_type="fast")
        
        current_memory = await self.get_memory(user_id, workspace_id)
        current_summary = current_memory.recent_context_summary if current_memory else "No previous context."

        prompt = f"""
        Current Conversation Summary: {current_summary}
        
        New Interaction: {new_interaction}
        
        Task: Create a one-paragraph updated summary that combines the old summary with the new interaction.
        Keep it concise and focus only on facts, names, and topics discussed.
        
        Updated Summary:
        """
        
        try:
            new_summary = await llm.chat_completion("You are a memory consolidation engine.", prompt)
            
            async with async_session() as session:
                from sqlalchemy import update
                from backend.models.user import User # Ensure User model exists or use upsert
                
                # Check if we need to create or update
                if not current_memory:
                    from backend.core.database import upsert_idempotent
                    await upsert_idempotent(
                        session,
                        UserMemory,
                        lookup_fields={"id": user_id, "workspace_id": workspace_id},
                        update_fields={"recent_context_summary": new_summary, "last_updated_at": datetime.utcnow()}
                    )
                else:
                    stmt = update(UserMemory).where(UserMemory.id == user_id).values(
                        recent_context_summary=new_summary,
                        last_updated_at=datetime.utcnow()
                    )
                    await session.execute(stmt)
                    await session.commit()
                    
            logger.info(f"Memory consolidated for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to consolidate memory: {e}")
