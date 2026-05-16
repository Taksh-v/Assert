import logging
from typing import List, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.knowledge_object import KnowledgeObject
from datetime import datetime

logger = logging.getLogger(__name__)

class EntityResolver:
    """
    Blueprint Layer 7: Entity Resolution & Knowledge Object Builder.
    Resolves extracted entities into unique KnowledgeObjects and links them to documents.
    """

    async def resolve_and_link(self, session: AsyncSession, workspace_id: str, document_id: str, entities: List[Dict[str, Any]]):
        """
        Merge extracted entities into the Knowledge Object registry.
        """
        if not entities:
            return

        for entity_data in entities:
            name = entity_data.get("name")
            e_type = entity_data.get("type", "General")
            
            if not name:
                continue

            # 1. Normalize name (Case-insensitive, stripped)
            normalized_name = name.strip()
            
            # 2. Check for existing KnowledgeObject in this workspace
            stmt = select(KnowledgeObject).where(
                KnowledgeObject.workspace_id == workspace_id,
                KnowledgeObject.name == normalized_name,
                KnowledgeObject.type == e_type
            )
            result = await session.execute(stmt)
            obj = result.scalars().first()

            if obj:
                # Merge: Update relationships
                source_ids = list(obj.source_document_ids or [])
                if document_id not in source_ids:
                    source_ids.append(document_id)
                    obj.source_document_ids = source_ids
                    obj.updated_at = datetime.utcnow()
                
                logger.debug(f"Merged entity '{normalized_name}' into existing KnowledgeObject")
            else:
                # Create: New KnowledgeObject
                new_obj = KnowledgeObject(
                    workspace_id=workspace_id,
                    name=normalized_name,
                    type=e_type,
                    source_document_ids=[document_id],
                    properties=entity_data.get("properties", {})
                )
                session.add(new_obj)
                logger.info(f"Created new KnowledgeObject: '{normalized_name}' ({e_type})")
        
        await session.commit()
