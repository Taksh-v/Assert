import logging
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.knowledge_object import KnowledgeObject
from backend.ingestion.embedder import Embedder
from backend.core.llm_client import LLMClient
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

class EntityResolver:
    """
    Blueprint Layer 7 & 10: Advanced Entity Resolution.
    Resolves extracted entities into unique KnowledgeObjects using semantic 
    similarity and LLM verification.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.llm = LLMClient()
        self.threshold_auto_merge = 0.92
        self.threshold_llm_verify = 0.75

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2: return 0.0
        a = np.array(v1)
        b = np.array(v2)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    async def resolve_and_link(self, session: AsyncSession, workspace_id: str, document_id: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge extracted entities into the Knowledge Object registry and return canonicalized entities.
        """
        if not entities:
            return []

        resolved_entities = []

        # 1. Fetch all existing KnowledgeObjects for this workspace
        stmt = select(KnowledgeObject).where(KnowledgeObject.workspace_id == workspace_id)
        result = await session.execute(stmt)
        existing_objects = result.scalars().all()
        
        for entity_data in entities:
            name = entity_data.get("name")
            category = entity_data.get("category", "GENERAL")
            e_type = entity_data.get("type", "concept")
            
            if not name:
                continue

            normalized_name = name.strip()
            resolved_obj = None

            # 2. Exact Match Check
            for obj in existing_objects:
                if obj.title.lower() == normalized_name.lower() and obj.type == e_type:
                    resolved_obj = obj
                    break
            
            # 3. Semantic Match Check
            if not resolved_obj and existing_objects:
                # Use async embedding to avoid blocking
                new_emb = (await self.embedder.aembed([normalized_name]))[0]
                best_score = 0
                best_match = None
                
                for obj in existing_objects:
                    if obj.type != e_type: continue
                    obj_emb = (await self.embedder.aembed([obj.title]))[0]
                    score = self._cosine_similarity(new_emb, obj_emb)
                    if score > best_score:
                        best_score = score
                        best_match = obj
                
                if best_score >= self.threshold_auto_merge:
                    resolved_obj = best_match
                elif best_score >= self.threshold_llm_verify:
                    is_same = await self._llm_verify_identity(normalized_name, best_match.title, e_type)
                    if is_same:
                        resolved_obj = best_match

            # 4. Finalize Resolution & Prepare Return Data
            canonical_name = normalized_name
            if resolved_obj:
                canonical_name = resolved_obj.title
                # Update existing object
                source_ids = list(resolved_obj.source_document_ids or [])
                if document_id not in source_ids:
                    source_ids.append(document_id)
                    resolved_obj.source_document_ids = source_ids
                
                existing_entities = list(resolved_obj.entities or [])
                if entity_data not in existing_entities:
                    existing_entities.append(entity_data)
                    resolved_obj.entities = existing_entities
                
                resolved_obj.updated_at = datetime.utcnow()
            else:
                # Create new
                new_obj = KnowledgeObject(
                    workspace_id=workspace_id,
                    title=normalized_name,
                    type=e_type,
                    summary=entity_data.get("summary", ""),
                    entities=[entity_data],
                    source_document_ids=[document_id]
                )
                session.add(new_obj)
                await session.flush()
                existing_objects.append(new_obj)
            
            # Add to resolved list for Graph Store
            res_entity = entity_data.copy()
            res_entity["name"] = canonical_name
            resolved_entities.append(res_entity)
        
        await session.commit()
        return resolved_entities

    async def _llm_verify_identity(self, name1: str, name2: str, e_type: str) -> bool:
        """Use LLM to confirm if two entity names refer to the same logical business concept."""
        prompt = f"""
        Are these two {e_type} entities referring to the same logical thing in an enterprise context?
        
        Entity 1: {name1}
        Entity 2: {name2}
        
        Consider common abbreviations, synonyms, and naming variations.
        Output ONLY "YES" or "NO".
        """
        try:
            res = await self.llm.chat_completion(prompt, "")
            return "YES" in res.upper()
        except Exception as e:
            logger.warning(f"LLM identity verification failed: {e}")
            return False
