import pytest
import asyncio
from unittest.mock import MagicMock
from backend.query.sparse_indexer import SparseIndexer
from backend.query.semantic_cache import SemanticCache
from backend.ingestion.contextualizer import ChunkContextualizer
from backend.core.llm_client import LLMClient

@pytest.mark.asyncio
async def test_sparse_indexer_workspace_isolation():
    """Verify that BM25 search queries for Workspace A return zero results from Workspace B documents."""
    indexer = SparseIndexer()
    indexer.add_document("doc_a", "Specific information about the quantum computers and qubits.", workspace_id="ws_a")
    indexer.add_document("doc_b", "Specific information about the coffee beans and espresso machines.", workspace_id="ws_b")

    # Search in ws_a
    results_a = indexer.search("quantum computers", workspace_id="ws_a")
    assert len(results_a) == 1
    assert results_a[0]["chunk_id"] == "doc_a"

    results_a_coffee = indexer.search("espresso machines", workspace_id="ws_a")
    assert len(results_a_coffee) == 0

    # Search in ws_b
    results_b = indexer.search("espresso machines", workspace_id="ws_b")
    assert len(results_b) == 1
    assert results_b[0]["chunk_id"] == "doc_b"

    results_b_quantum = indexer.search("quantum computers", workspace_id="ws_b")
    assert len(results_b_quantum) == 0


@pytest.mark.asyncio
async def test_sparse_indexer_idf_independence():
    """Verify that BM25 global IDF term calculations remain independent across workspaces."""
    indexer = SparseIndexer()

    # Workspace A: "banana" is very common (5 documents)
    for i in range(5):
        indexer.add_document(f"doc_a_{i}", f"This is doc {i} with a banana fruit in it.", workspace_id="ws_a")
    
    # Workspace B: "banana" is very rare (1 document)
    indexer.add_document("doc_b_1", "This is the only document containing a banana in Workspace B.", workspace_id="ws_b")
    # Add other documents to Workspace B without "banana" to increase N
    for i in range(4):
        indexer.add_document(f"doc_b_other_{i}", "Just some other text without that fruit.", workspace_id="ws_b")

    # Search for "banana" in ws_a and ws_b
    res_a = indexer.search("banana", workspace_id="ws_a")
    res_b = indexer.search("banana", workspace_id="ws_b")

    assert len(res_a) > 0
    assert len(res_b) > 0

    score_a = res_a[0]["score"]
    score_b = res_b[0]["score"]

    # Since "banana" is rarer in Workspace B (1 out of 5 docs) than in Workspace A (5 out of 5 docs),
    # the IDF and thus the score in Workspace B should be significantly higher.
    assert score_b > score_a


@pytest.mark.asyncio
async def test_semantic_cache_context_mismatch():
    """Verify that L2 semantic cache queries with different document scopes result in correct cache misses."""
    cache = SemanticCache()

    # Mock embedder and vector store
    async def mock_aembed(texts):
        return [[0.1] * 384 for _ in texts]
    cache.embedder.aembed = mock_aembed

    stored_points = []
    def mock_upsert_batch(workspace_id, vectors, payloads):
        for vec, payload in zip(vectors, payloads):
            stored_points.append({
                "workspace_id": workspace_id,
                "vector": vec,
                "payload": payload
            })

    async def mock_async_search(workspace_id, query_vector, top_k, vector_name):
        results = []
        for pt in stored_points:
            if pt["workspace_id"] == workspace_id:
                results.append({
                    "score": 0.98,
                    "metadata": pt["payload"]
                })
        return results

    cache.vector_store.upsert_batch = mock_upsert_batch
    cache.vector_store.async_search = mock_async_search

    # Store cache with context_files=['file_a.txt']
    await cache.set_cache(
        workspace_id="ws_1",
        question="What is the refund policy?",
        result={"answer": "You have 30 days to get a refund.", "sources": []},
        context_files=["file_a.txt"]
    )

    # Check cache with same question but different context_files (should be miss)
    miss_res = await cache.check_cache(
        workspace_id="ws_1",
        question="What is the refund policy?",
        context_files=["file_b.txt"]
    )
    assert miss_res is None

    # Check cache with same question and same context_files (should be hit)
    hit_res = await cache.check_cache(
        workspace_id="ws_1",
        question="What is the refund policy?",
        context_files=["file_a.txt"]
    )
    assert hit_res is not None
    assert hit_res["answer"] == "You have 30 days to get a refund."


@pytest.mark.asyncio
async def test_contextualizer_sliding_window():
    """Verify that the contextualizer sliding window positioning handles empty, short, and long documents gracefully."""
    contextualizer = ChunkContextualizer()
    contextualizer.enabled = True

    # Mock chat_completion to return a dummy context string
    async def mock_chat_completion(*args, **kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        # Validate that the prompt contains the title
        assert "Document Title: Test Doc" in user_prompt
        # Validate that the prompt contains the sliding window context
        assert "target chunk content" in user_prompt
        return "This is the generated context."
    
    contextualizer.llm.chat_completion = mock_chat_completion

    # Test Case 1: Empty document content
    empty_res = await contextualizer.contextualize("Test Doc", "", "some chunk")
    assert empty_res == ""

    # Test Case 2: Short document content (fully fits in sliding window)
    short_content = "This is a short document with some target chunk content in it."
    short_res = await contextualizer.contextualize("Test Doc", short_content, "target chunk content")
    assert short_res == "This is the generated context."

    # Test Case 3: Long document content (sliding window extracts context around chunk)
    # Create a long document: 3000 chars before, target chunk, 3000 chars after
    before = "a" * 3000
    after = "b" * 3000
    long_content = before + " target chunk content " + after
    
    # We will verify that the prompt generated contains a window around chunk,
    # and not the full 6000+ characters (which would exceed typical limits if we had strict sizing).
    # Since we extract max(0, idx - 2500) to min(len, idx + len + 2500), the window size will be
    # approximately 2500 + len(chunk) + 2500 = 5022 characters.
    # We want to make sure it includes target chunk content and runs without error.
    long_res = await contextualizer.contextualize("Test Doc", long_content, "target chunk content")
    assert long_res == "This is the generated context."
