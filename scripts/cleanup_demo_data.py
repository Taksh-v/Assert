import os
import sys
import json
import sqlite3

# Add current directory to PYTHONPATH
sys.path.append(os.getcwd())

from backend.core.config import get_settings
from backend.core.security import decrypt_config
from backend.core.vector_store import get_qdrant_client_ctx

def main():
    settings = get_settings()
    db_path = "data/assest_dev.db"
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    print("🌱 Connecting to SQLite database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Retrieve all connectors
    cursor.execute("SELECT id, type, config FROM connectors;")
    rows = cursor.fetchall()

    connectors_to_delete = []
    for cid, ctype, cconfig in rows:
        try:
            config = decrypt_config(cconfig)
        except Exception:
            config = {}

        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                pass

        if not isinstance(config, dict):
            config = {}

        # Mark as delete if marked mock or test
        if config.get("mock") or "mock" in cid or "test_conn" in cid or cid.startswith("test-"):
            connectors_to_delete.append(cid)

    print(f"👉 Mock/Test connectors found to delete: {connectors_to_delete}")

    # 2. Identify orphaned documents (where connector_id is not in connectors table)
    cursor.execute("SELECT id FROM documents WHERE connector_id NOT IN (SELECT id FROM connectors);")
    orphaned_doc_ids = [r[0] for r in cursor.fetchall()]
    print(f"👉 Orphaned documents found: {len(orphaned_doc_ids)}")

    # 3. Compile all documents to delete
    doc_ids_to_delete = list(orphaned_doc_ids)
    if connectors_to_delete:
        placeholders = ",".join("?" for _ in connectors_to_delete)
        cursor.execute(f"SELECT id FROM documents WHERE connector_id IN ({placeholders});", connectors_to_delete)
        doc_ids_to_delete.extend([r[0] for r in cursor.fetchall()])

    doc_ids_to_delete = list(set(doc_ids_to_delete))
    print(f"👉 Total documents to purge from database: {len(doc_ids_to_delete)}")

    # 4. Perform SQLite Deletes
    cursor.execute("PRAGMA foreign_keys = ON;")

    if doc_ids_to_delete:
        chunks_deleted = 0
        for i in range(0, len(doc_ids_to_delete), 500):
            batch = doc_ids_to_delete[i:i+500]
            placeholders = ",".join("?" for _ in batch)
            cursor.execute(f"DELETE FROM chunks WHERE document_id IN ({placeholders});", batch)
            chunks_deleted += cursor.rowcount
        print(f"✅ Deleted {chunks_deleted} chunks from SQLite.")

        docs_deleted = 0
        for i in range(0, len(doc_ids_to_delete), 500):
            batch = doc_ids_to_delete[i:i+500]
            placeholders = ",".join("?" for _ in batch)
            cursor.execute(f"DELETE FROM documents WHERE id IN ({placeholders});", batch)
            docs_deleted += cursor.rowcount
        print(f"✅ Deleted {docs_deleted} documents from SQLite.")

    if connectors_to_delete:
        placeholders = ",".join("?" for _ in connectors_to_delete)
        cursor.execute(f"DELETE FROM sync_runs WHERE connector_id IN ({placeholders});", connectors_to_delete)
        print(f"✅ Deleted {cursor.rowcount} sync runs from SQLite.")

        cursor.execute(f"DELETE FROM connectors WHERE id IN ({placeholders});", connectors_to_delete)
        print(f"✅ Deleted {cursor.rowcount} connectors from SQLite.")

    conn.commit()
    conn.close()

    # 5. Clean up Qdrant collections
    print("🌱 Initializing Qdrant client connection...")
    with get_qdrant_client_ctx() as qdrant_client:
        if qdrant_client:
            try:
                # Import models
                from qdrant_client.http import models
                
                # Delete points by workspace/is_active or recreate the collection to clear out old demo vectors
                # Since we want to clear ALL legacy data (except from currently active connectors),
                # recreating the collections is the cleanest way to guarantee zero demo vector leak.
                collection_name = settings.qdrant_collection_name
                print(f"🔥 Recreating Qdrant collection: {collection_name} to clear stale embeddings...")
                try:
                    qdrant_client.delete_collection(collection_name)
                    print(f"✅ Deleted Qdrant collection: {collection_name}")
                except Exception as e:
                    print(f"⚠️ Collection deletion failed (might not exist): {e}")
                
                # Re-initialize Qdrant collections
                from backend.core.vector_store import initialize_qdrant_collections
                initialize_qdrant_collections()
                print("✅ Successfully recreated and initialized fresh Qdrant collections.")
            except Exception as e:
                print(f"❌ Failed to clear Qdrant collections: {e}")
        else:
            print("⚠️ Qdrant client not available; skipping vector purge.")

    print("🎉 Cleanup completed successfully!")

if __name__ == "__main__":
    main()
