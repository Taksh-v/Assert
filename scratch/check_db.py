from dotenv import load_dotenv
load_dotenv()
import os
import asyncio
from sqlalchemy import text
import sys
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from backend.core.database import AsyncSessionLocal, engine

async def main():
    print(f"Engine URL: {engine.url}")
    async with AsyncSessionLocal() as session:
        doc_count = await session.execute(text("SELECT count(*) FROM documents"))
        print(f"Total documents: {doc_count.scalar()}")
        
        chunk_count = await session.execute(text("SELECT count(*) FROM document_chunks"))
        print(f"Total chunks: {chunk_count.scalar()}")
        
        chunk_preview = await session.execute(text("SELECT id, document_id, content FROM document_chunks LIMIT 1"))
        for row in chunk_preview:
            print(f"Chunk: {row}")

if __name__ == "__main__":
    asyncio.run(main())
