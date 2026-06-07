import asyncio
import logging
import uuid
from datetime import datetime
from backend.core.database import init_db, async_session
from backend.models.document import Document
from backend.ingestion.pipeline import IngestionPipeline
from backend.retrieval.orchestrator import RetrievalOrchestrator
from backend.reasoning.orchestrator import ReasoningOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FullSystemVerification")

async def verify():
    logger.info("🚀 Starting Full System Verification (Phases 1-3)...")
    
    # 1. Initialize Tables
    await init_db()
    workspace_id = "test_ws_" + str(uuid.uuid4())[:8]
    
    pipeline = IngestionPipeline()
    retrieval_orchestrator = RetrievalOrchestrator()
    reasoning_orchestrator = ReasoningOrchestrator()
    
    # 2. Fresh Qdrant Collection (Layer 8)
    try:
        pipeline.vector_store.client.delete_collection(pipeline.vector_store.collection_name)
    except:
        pass
    pipeline.vector_store.create_collection(384)

    connector_id = "test_conn_" + str(uuid.uuid4())[:8]
    # Create dummy workspace and connector for DB constraints
    from backend.models.workspace import Workspace
    from backend.models.connector import Connector, ConnectorType, ConnectorStatus
    async with async_session() as session:
        ws = Workspace(id=workspace_id, name="Test Workspace", slug=workspace_id)
        session.add(ws)
        conn = Connector(
            id=connector_id, 
            workspace_id=workspace_id, 
            type=ConnectorType.NOTION,
            config={},
            status=ConnectorStatus.ACTIVE
        )
        session.add(conn)
        await session.commit()
    logger.info("\n--- Phase 1: Ingesting Knowledge ---")
    
    # Document 1: Infrastructure State
    doc_1_content = """
    Infrastructure Report - May 2026
    The Auth Service (v2.1) is now active on the production cluster.
    It depends on the User-DB and the Redis-Cache.
    On May 10, we performed a Database Migration to support v2.1.
    The migration caused a minor spike in latency.
    """
    
    # Document 2: Incident Report
    doc_2_content = """
    Incident Log - May 12, 2026
    The Authentication API experienced high latency for 2 hours.
    This was linked to the recent Database Migration.
    The DevOps Team mitigated this by scaling the production cluster.
    """
    
    # Mocking RawDocument objects for pipeline
    class MockRawDoc:
        def __init__(self, title, content, source_url):
            self.title = title
            self.raw_content = content
            self.source_url = source_url
            self.source_type = "notion"
            self.content_format = "text"
            self.metadata = {}
            self.permissions = {}
            self.visibility = "private"
            self.tier = 1

    raw_doc_1 = MockRawDoc("Infra Report", doc_1_content, "https://notion.com/infra")
    raw_doc_2 = MockRawDoc("Incident Log", doc_2_content, "https://notion.com/incident")

    logger.info("Processing Document 1 (Phase 1 Resolution & Events)...")
    await pipeline._process_document(raw_doc_1, workspace_id, connector_id=connector_id)
    
    logger.info("Processing Document 2 (Phase 1 Canonicalization)...")
    await pipeline._process_document(raw_doc_2, workspace_id, connector_id=connector_id)

    # Verify Knowledge Objects
    from backend.models.knowledge_object import KnowledgeObject
    from backend.models.knowledge_event import KnowledgeEvent
    
    async with async_session() as session:
        from sqlalchemy import select
        ko_stmt = select(KnowledgeObject).where(KnowledgeObject.workspace_id == workspace_id)
        kos = (await session.execute(ko_stmt)).scalars().all()
        logger.info(f"✅ PHASE 1: Created {len(kos)} Knowledge Objects.")
        for ko in kos:
            logger.info(f"  - Object: {ko.title} ({ko.type})")

        ev_stmt = select(KnowledgeEvent).where(KnowledgeEvent.workspace_id == workspace_id)
        evs = (await session.execute(ev_stmt)).scalars().all()
        logger.info(f"✅ PHASE 1: Created {len(evs)} Temporal Events.")
        for ev in evs:
            logger.info(f"  - Event: [{ev.timestamp}] {ev.title} ({ev.event_type})")

    # --- PHASE 2: RETRIEVAL INTELLIGENCE ---
    logger.info("\n--- Phase 2: Intelligence Retrieval ---")
    query = "Why did the Auth Service experience latency?"
    
    context = await retrieval_orchestrator.retrieve_reasoning_context(query, workspace_id)
    logger.info("✅ PHASE 2: Retrieval Context Synthesized.")
    logger.info(f"Context Snippet: {context[:200]}...")
    
    if "Database Migration" in context and "Auth Service" in context:
        logger.info("✅ PHASE 2: Multi-stream retrieval (Vector + Temporal) successful.")
    else:
        logger.warning("⚠️ PHASE 2: Missing expected cross-stream context.")

    # --- PHASE 3: REASONING INFRASTRUCTURE ---
    logger.info("\n--- Phase 3: Autonomous Reasoning Swarm ---")
    reasoning_query = "Analyze the cause of the Auth Service latency and provide a recommendation."
    
    result = await reasoning_orchestrator.run(reasoning_query, workspace_id)
    
    logger.info(f"✅ PHASE 3: Reasoning Swarm Completed in {result['iterations']} iterations.")
    logger.info(f"Confidence: {result['confidence'] * 100}%")
    logger.info("\n--- FINAL INTELLIGENCE REPORT ---")
    logger.info(result['answer'])
    
    logger.info("\n🏆 Full System Verification Complete!")

if __name__ == "__main__":
    asyncio.run(verify())
