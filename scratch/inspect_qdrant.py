import asyncio
import logging
from backend.core.vector_store import get_qdrant_client_ctx
from backend.core.config import get_settings
from qdrant_client.http import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inspect_qdrant")

settings = get_settings()

async def inspect():
    with get_qdrant_client_ctx() as client:
        if not client:
            logger.error("Failed to connect to Qdrant.")
            return
            
        # List all collections
        collections = client.get_collections().collections
        logger.info(f"Available collections: {[c.name for c in collections]}")
        
        for coll in collections:
            # Count points in collection
            count_res = client.count(
                collection_name=coll.name,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="workspace_id",
                            match=models.MatchValue(value="929271f5-82ab-460b-86e2-4bba7e2e8d1d")
                        )
                    ]
                )
            )
            logger.info(f"Collection '{coll.name}' has {count_res.count} points for workspace 929271f5-82ab-460b-86e2-4bba7e2e8d1d")
            
            # Print a few points
            if count_res.count > 0:
                points_res = client.scroll(
                    collection_name=coll.name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="workspace_id",
                                match=models.MatchValue(value="929271f5-82ab-460b-86e2-4bba7e2e8d1d")
                            )
                        ]
                    ),
                    limit=5,
                    with_payload=True,
                    with_vectors=False
                )
                for pt in points_res[0]:
                    logger.info(f"Point id={pt.id}, payload={pt.payload}")

if __name__ == "__main__":
    asyncio.run(inspect())
