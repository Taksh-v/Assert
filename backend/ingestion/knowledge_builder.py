import logging
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from backend.core.database import async_session
from backend.models.document import Document
from backend.models.knowledge_object import KnowledgeObject
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class KnowledgeBuilder:
    """
    Blueprint Layer 7: Knowledge Object Builder.
    Aggregates disparate chunks and documents into high-fidelity "Knowledge Objects".
    """
    
    def __init__(self):
        self.llm = LLMClient()

    async def discover_and_build(self, workspace_id: str):
        """
        Layer 7: High-Fidelity Synthesis.
        Enriches existing KnowledgeObjects by synthesizing content from multiple source documents.
        """
        logger.info(f"Starting Knowledge Object Synthesis for workspace: {workspace_id}")
        
        async with async_session() as session:
            # 1. Fetch KnowledgeObjects that have multiple sources but no deep summary
            stmt = select(KnowledgeObject).where(
                KnowledgeObject.workspace_id == workspace_id
            )
            result = await session.execute(stmt)
            k_objects = result.scalars().all()
            
            for obj in k_objects:
                source_ids = obj.source_document_ids or []
                if len(source_ids) < 2:
                    continue # Only synthesize for cross-linked concepts
                
                # Check if we already have a long, professional summary (simplified check)
                if obj.summary and len(obj.summary) > 200:
                    continue

                logger.info(f"Synthesizing deep knowledge for: {obj.title} (Sources: {len(source_ids)})")
                
                # 2. Fetch full text for source documents
                doc_stmt = select(Document).where(Document.id.in_(source_ids))
                doc_res = await session.execute(doc_stmt)
                docs = doc_res.scalars().all()
                
                # Build context (using titles and snippets)
                context_parts = []
                for d in docs:
                    context_parts.append(f"--- Document: {d.title} ---\n{d.summary or 'No summary available.'}")
                
                context = "\n\n".join(context_parts)
                
                prompt = f"""
                You are a Senior Knowledge Engineer. Your task is to synthesize a high-fidelity 'Knowledge Object' from multiple source documents.
                
                Title: {obj.title}
                Category: {obj.type}
                
                Source Summaries:
                {context}
                
                Task:
                1. Write a professional, executive-level synthesis (2-3 paragraphs).
                2. Identify key organizational relationships (who owns this, which teams use it).
                3. List technical dependencies or business impact.
                4. Refine the 'type' if necessary (Workflow, System, Project, Team, API).
                
                Output ONLY valid JSON:
                {{
                  "refined_type": "...",
                  "synthesis": "...",
                  "relationships": ["...", "..."],
                  "dependencies": ["...", "..."]
                }}
                """
                
                try:
                    res_json = await self.llm.chat_completion(prompt, "")
                    data = json.loads(res_json)
                    
                    # Update Knowledge Object
                    obj.summary = data.get("synthesis", obj.summary)
                    obj.type = data.get("refined_type", obj.type)
                    
                    # Store extra metadata in a structured field if available (using entities/topics for now)
                    obj.entities = list(set((obj.entities or []) + data.get("relationships", []) + data.get("dependencies", [])))
                    
                    obj.updated_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"Successfully synthesized knowledge for: {obj.title}")
                    
                except Exception as e:
                    logger.error(f"Failed synthesis for {obj.title}: {e}")
                    await session.rollback()
