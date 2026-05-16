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
        Scan recently ingested documents and discover concepts to promote to Knowledge Objects.
        """
        logger.info(f"Starting Knowledge Object Discovery for workspace: {workspace_id}")
        
        async with async_session() as session:
            # 1. Fetch recent documents and their metadata
            stmt = select(Document).where(Document.workspace_id == workspace_id).limit(50)
            result = await session.execute(stmt)
            docs = result.scalars().all()
            
            if not docs:
                return
            
            # 2. Group by Topic (Simple heuristic for now)
            topic_map = {}
            for doc in docs:
                # Assuming metadata contains 'topics' from Layer 5
                # We'll use a more advanced entity-matching logic in production
                topics = ["General"] # Fallback
                
                # Try to find topics from any related chunks or metadata (simplifying for demo)
                if doc.title:
                    topics = [doc.title.split(":")[0].strip()]
                
                for topic in topics:
                    if topic not in topic_map:
                        topic_map[topic] = []
                    topic_map[topic].append(doc)
            
            # 3. For each group, synthesize a Knowledge Object
            for topic, group_docs in topic_map.items():
                if len(group_docs) < 2:
                    continue # Only build objects for cross-linked knowledge
                
                logger.info(f"Synthesizing Knowledge Object for concept: {topic}")
                
                # Build context for LLM
                context = "\n".join([f"- {d.title} (Source: {d.source_url})" for d in group_docs])
                
                prompt = f"""
                You are a Knowledge Architect. Analyze these related documents and synthesize them into a single 'Knowledge Object'.
                
                Concept: {topic}
                Documents:
                {context}
                
                Identify:
                1. Type: (workflow, process, policy, incident, or project)
                2. Unified Title: A professional name for this concept.
                3. Executive Summary: A 2-3 sentence summary of the combined knowledge.
                4. Key Entities: Specific people, tools, or products involved.
                
                Output ONLY valid JSON:
                {{
                  "type": "...",
                  "title": "...",
                  "summary": "...",
                  "entities": ["...", "..."]
                }}
                """
                
                try:
                    res_json = await self.llm.chat_completion(prompt, "")
                    data = json.loads(res_json)
                    
                    # Create or update Knowledge Object
                    new_obj = KnowledgeObject(
                        workspace_id=workspace_id,
                        type=data.get("type", "concept"),
                        title=data.get("title", topic),
                        summary=data.get("summary", ""),
                        entities=data.get("entities", []),
                        source_document_ids=[d.id for d in group_docs],
                        topics=[topic]
                    )
                    
                    session.add(new_obj)
                    await session.commit()
                    logger.info(f"Successfully built Knowledge Object: {new_obj.title}")
                    
                except Exception as e:
                    logger.error(f"Failed to synthesize Knowledge Object for {topic}: {e}")
