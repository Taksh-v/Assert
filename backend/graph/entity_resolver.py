import logging
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from backend.core.database import async_session
from backend.models.knowledge_object import KnowledgeObject

logger = logging.getLogger(__name__)

class EntityResolver:
    """
    Phase 1: Knowledge Formation Layer - Entity Resolution & Linking.
    Canonicalizes entities across documents to build a unified graph.
    """

    async def resolve_and_link(
        self, 
        session: Any, 
        workspace_id: str, 
        document_id: str, 
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Resolves a list of raw entities against the existing knowledge base.
        """
        resolved_list = []
        
        for entity_data in entities:
            name = entity_data.get("name")
            e_type = entity_data.get("type", "concept")
            
            if not name: continue
            
            # 1. Search for existing KnowledgeObject (Canonicalization)
            stmt = select(KnowledgeObject).where(
                KnowledgeObject.workspace_id == workspace_id,
                KnowledgeObject.title == name,
                KnowledgeObject.type == e_type
            )
            result = await session.execute(stmt)
            existing_ko = result.scalars().first()
            
            if existing_ko:
                logger.info(f"Resolved existing entity: {name}")
                ko_id = existing_ko.id
            else:
                # 2. Create new KnowledgeObject if not found
                logger.info(f"Creating new canonical entity: {name}")
                ko_id = str(uuid.uuid4())
                new_ko = KnowledgeObject(
                    id=ko_id,
                    workspace_id=workspace_id,
                    title=name,
                    type=e_type,
                    summary=entity_data.get("description", "")
                )
                session.add(new_ko)
            
            resolved_list.append({
                "id": ko_id,
                "name": name,
                "type": e_type,
                "original_data": entity_data
            })
            
        await session.commit()
        return resolved_list
