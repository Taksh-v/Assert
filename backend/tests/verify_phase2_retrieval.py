import asyncio
import logging
import uuid
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.query.retriever import Retriever
from backend.ingestion.pipeline import IngestionPipeline
from backend.core.database import async_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockRawDoc:
    def __init__(self, title, content, source_url):
        self.title = title
        self.raw_content = content
        self.content = content
        self.source_url = source_url
        self.source_id = str(uuid.uuid4())
        self.source_type = "test"
        self.content_format = "text"
        self.tier = 1

async def verify_phase2():
    logger.info("🚀 Starting Phase 2: Retrieval Intelligence Verification")
    
    workspace_id = f"retrieval_ws_{uuid.uuid4().hex[:8]}"
    pipeline = IngestionPipeline()
    retriever = Retriever()
    
    # 1. Seed Data for Retrieval
    seed_docs = [
        MockRawDoc("Company Vacation Policy", "Employees get 25 days of paid leave per year. Requests must be submitted 2 weeks in advance.", "https://hr.corp/vacation"),
        MockRawDoc("Project X Architecture", "Project X uses a microservices architecture with a React frontend and Go backend.", "https://wiki.corp/project-x")
    ]
    
    try:
        logger.info("Seeding test data...")
        for doc in seed_docs:
            await pipeline._process_document(doc, workspace_id)
        
        # Give a small delay for local Qdrant indexing if needed (though local is usually instant)
        await asyncio.sleep(1)

        # 2. Test 'Specific' Intent Retrieval
        logger.info("Testing specific intent: 'How many days of leave do I get?'")
        results_specific = await retriever.search("How many days of leave do I get?", workspace_id, top_k=2)
        
        logger.info(f"Specific Results: {len(results_specific)}")
        # Check for scrubbed content since Phase 1 verified PII scrubbing is active
        found_vacation = any("<DATE_TIME>" in res.content for res in results_specific)
        assert found_vacation, "Failed to find vacation policy for specific query (Note: should be scrubbed to <DATE_TIME>)"
        logger.info("✅ Specific intent retrieval successful (Scrubbed content found)")

        # 3. Test 'Broad' Intent Retrieval
        logger.info("Testing broad intent: 'Tell me about Project X'")
        results_broad = await retriever.search("Tell me about Project X", workspace_id, top_k=2)
        
        logger.info(f"Broad Results: {len(results_broad)}")
        found_arch = any("microservices" in res.content for res in results_broad)
        assert found_arch, "Failed to find project architecture for broad query"
        logger.info("✅ Broad intent retrieval successful")

        logger.info("🎉 Phase 2 Retrieval Verification SUCCESSFUL")
        return True

    except Exception as e:
        logger.error(f"❌ Phase 2 Retrieval Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(verify_phase2())
    sys.exit(0 if success else 1)
