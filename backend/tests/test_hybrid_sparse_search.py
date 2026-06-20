import asyncio
import pytest
import threading
from types import SimpleNamespace
from backend.query.sparse_indexer import SparseIndexer, get_sparse_indexer
from backend.query.retriever import Retriever, RetrievalResult
from backend.models.chunk import Chunk as DBChunk
from backend.core.database import async_session

@pytest.mark.asyncio
async def test_sparse_indexer_crud():
    indexer = SparseIndexer()
    indexer.add_document("doc1", "The quick brown fox jumps over the lazy dog.")
    indexer.add_document("doc2", "Clean code is key. Python coding standards are important.")
    
    assert indexer.N == 2
    assert "doc1" in indexer.doc_texts
    assert "doc2" in indexer.doc_texts
    
    # Tokenization check (stopwords filtered)
    tokens_doc1 = indexer.tokenize("The quick brown fox jumps over the lazy dog.")
    assert "the" not in tokens_doc1
    assert "quick" in tokens_doc1
    
    # Search check
    results = indexer.search("python code")
    assert len(results) > 0
    assert results[0]["chunk_id"] == "doc2"
    
    # Remove doc check
    indexer.remove_document("doc2")
    assert indexer.N == 1
    assert "doc2" not in indexer.doc_texts
    
    results = indexer.search("python code")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_sparse_indexer_thread_safety():
    indexer = SparseIndexer()
    
    def worker(worker_id):
        for i in range(50):
            indexer.add_document(f"worker_{worker_id}_doc_{i}", f"This is some text for worker {worker_id} and iteration {i}")
            indexer.search("text worker")
            
    threads = []
    for t_id in range(5):
        t = threading.Thread(target=worker, args=(t_id,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert indexer.N == 250

@pytest.mark.asyncio
async def test_retriever_hybrid_and_parent_mapping():
    # Instantiate retriever
    retriever = Retriever()
    
    # Mock embedding and vector store
    async def mock_aembed(chunks):
        return [[0.1] * 384 for _ in chunks]
    retriever.embedder.aembed = mock_aembed
    
    async def mock_async_search(workspace_id, query_vector, top_k, user_id, vector_name, *args, **kwargs):
        return [
            {
                "chunk_id": "child_1",
                "text": "<context>Guide</context>\nGET /v1/users retrieves user records.",
                "score": 0.9,
                "metadata": {
                    "title": "API Guide",
                    "source_url": "https://api/guide",
                    "parent_id": "parent_1"
                }
            }
        ]
    retriever.vector_store.async_search = mock_async_search
    
    # Setup global sparse indexer with mock child document
    sparse_indexer = get_sparse_indexer()
    sparse_indexer.add_document("child_1", "GET /v1/users retrieves user records.")
    
    # We will mock the database session to return the child and parent DBChunk objects
    # when queried during search retrieval and parent mapping
    import backend.query.retriever as retriever_module
    
    class FakeResult:
        def __init__(self, scalars_list):
            self._scalars = scalars_list
        def scalars(self):
            return FakeResult(self._scalars)
            
        def all(self):
            return self._scalars

    class FakeSession:
        async def execute(self, stmt):
            sql_str = str(stmt).lower()
            try:
                params = stmt.compile().params
            except Exception:
                params = {}
            
            is_parent = False
            for val in params.values():
                if isinstance(val, (list, tuple, set, dict)):
                    if "parent_1" in val:
                        is_parent = True
                elif val == "parent_1":
                    is_parent = True

            if is_parent or "parent_1" in sql_str:
                # Parent lookup
                return FakeResult([
                    DBChunk(
                        id="parent_1",
                        content="Full Section: This section describes user management. GET /v1/users retrieves user records. POST /v1/users creates users.",
                        parent_id=None,
                        document_title="API Guide",
                        source_url="https://api/guide",
                        tier=2
                    )
                ])
            else:
                # Keyword lookup (for child_1)
                return FakeResult([
                    DBChunk(
                        id="child_1",
                        content="GET /v1/users retrieves user records.",
                        parent_id="parent_1",
                        document_title="API Guide",
                        source_url="https://api/guide",
                        tier=2
                    )
                ])
                
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    original_session = retriever_module.async_session
    retriever_module.async_session = FakeSession
    
    try:
        results = await retriever.search(
            question="how to retrieve users",
            workspace_id="w-123",
            top_k=2
        )
        
        assert len(results) > 0
        hit = results[0]
        assert hit.chunk_id == "child_1"
        # Content MUST be mapped to parent content!
        assert "Full Section:" in hit.content
        assert "POST /v1/users" in hit.content
        assert hit.title == "API Guide"
        
    finally:
        retriever_module.async_session = original_session
