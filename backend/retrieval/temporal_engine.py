import logging
from typing import List, Dict, Any
from sqlalchemy import select, and_, or_
from backend.core.database import async_session
from backend.models.knowledge_event import KnowledgeEvent
from datetime import datetime

logger = logging.getLogger(__name__)

class TemporalEngine:
    """
    Layer 13: Temporal Retrieval Engine.
    Queries the timeline of organizational events and causality.
    """

    async def get_relevant_events(
        self, 
        workspace_id: str, 
        entities: List[str], 
        query: str = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events related to specific entities or query context.
        """
        async with async_session() as session:
            # Build search conditions
            conditions = [KnowledgeEvent.workspace_id == workspace_id]
            
            if entities:
                # Check if any entity is in the related_entity_ids JSON list
                entity_filters = [KnowledgeEvent.related_entity_ids.contains([ent]) for ent in entities]
                conditions.append(or_(*entity_filters))
            
            stmt = select(KnowledgeEvent).where(and_(*conditions)).order_by(KnowledgeEvent.timestamp.desc()).limit(limit)
            result = await session.execute(stmt)
            events = result.scalars().all()
            
            return [
                {
                    "event_id": e.id,
                    "title": e.title,
                    "type": e.event_type,
                    "timestamp": e.timestamp.isoformat(),
                    "description": e.description,
                    "metadata": e.metadata_json
                }
                for e in events
            ]

    async def get_timeline_context(self, workspace_id: str, entities: List[str]) -> str:
        """
        Format a timeline of events into a context string for the LLM.
        """
        events = await self.get_relevant_events(workspace_id, entities)
        if not events:
            return ""
            
        lines = ["### Organizational Timeline (Temporal Events):"]
        for e in events:
            lines.append(f"- [{e['timestamp']}] {e['type'].upper()}: {e['title']} - {e['description']}")
            
        return "\n".join(lines)
