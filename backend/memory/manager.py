import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.core.database import async_session
from backend.models.memory import AgenticMemory
from sqlalchemy import select, update

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Blueprint Layer 16: Agentic Memory Manager.
    Handles short-term and long-term memory persistence using local DB and Capsule Service.
    """

    def __init__(self):
        # In a real app, we would initialize the Capsule Service MCP client here
        pass

    async def store_observation(
        self, 
        workspace_id: str, 
        content: str, 
        memory_type: str = "observation",
        user_id: Optional[str] = None,
        importance: float = 0.5
    ) -> str:
        """
        Store a new piece of agentic memory.
        """
        async with async_session() as session:
            memory = AgenticMemory(
                workspace_id=workspace_id,
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                importance_score=importance
            )
            session.add(memory)
            await session.commit()
            logger.info(f"Agentic Memory Stored: [{memory_type}] {content[:50]}...")
            return memory.id

    async def get_relevant_memories(
        self, 
        workspace_id: str, 
        query: str,
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories relevant to the current context.
        In Layer 16, this would also use vector search on memories.
        """
        async with async_session() as session:
            # For now, simple recent memory retrieval
            # Ideally, we would vector-search the 'content' of memories
            stmt = select(AgenticMemory).where(
                AgenticMemory.workspace_id == workspace_id,
                AgenticMemory.user_id == user_id if user_id else True
            ).order_by(AgenticMemory.importance_score.desc(), AgenticMemory.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            memories = result.scalars().all()
            
            return [
                {
                    "type": m.memory_type,
                    "content": m.content,
                    "age_days": (datetime.utcnow() - m.created_at).days
                }
                for m in memories
            ]

    async def consolidate_to_capsule(self, workspace_id: str, tag: str):
        """
        Layer 16: Elite Persistence.
        Groups local memories and pushes them to the 'capsule-service' for cross-session availability.
        """
        # This would call mcp_capsule-service_create_capsule
        logger.info(f"Consolidating memories for {workspace_id} into Capsule: {tag}")
        pass
