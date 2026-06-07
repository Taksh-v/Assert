import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

async def verify_system():
    print("🔍 Verifying Assest System...")
    
    try:
        from backend.core.database import init_db, get_db, Base
        from backend.models import Workspace, Connector, Document, QueryLog
        from backend.ingestion.pii_scrubber import PIIScrubber
        from backend.ingestion.chunker import DocumentChunker
        from backend.ingestion.embedder import Embedder
        from backend.query.retriever import Retriever
        from backend.query.generator import Generator
        
        print("✅ All core modules imported successfully.")
        
        # Initialize Database
        print("⏳ Initializing database...")
        await init_db()
        print("✅ Database initialized successfully.")
        
        # Test PII Scrubber
        print("⏳ Testing PII Scrubber...")
        scrubber = PIIScrubber()
        text = "My phone number is 9876543210 and my email is test@example.com"
        scrubbed, entities = scrubber.scrub(text)
        print(f"   Original: {text}")
        print(f"   Scrubbed: {scrubbed}")
        print(f"   Entities: {entities}")
        
        # Test Chunker
        print("⏳ Testing Chunker...")
        chunker = DocumentChunker(chunk_size=20, chunk_overlap=5)
        chunks = chunker.chunk("This is a long sentence that should be split into multiple chunks for testing.")
        print(f"   Chunks: {chunks}")
        
        # Test Embedder (Mock/Local)
        print("⏳ Testing Embedder...")
        embedder = Embedder()
        embeddings = embedder.embed(["Hello world"])
        print(f"   Embedding size: {len(embeddings[0])}")
        
        print("\n🚀 Verification Complete: SYSTEM READY FOR DEVELOPMENT")
        
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_system())
