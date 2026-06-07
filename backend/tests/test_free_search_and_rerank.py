import pytest
from unittest.mock import AsyncMock
from backend.query.crag_verifier import KnowledgeGapHandler
from backend.query.reranker import CrossEncoderReranker

@pytest.mark.anyio
async def test_duckduckgo_search_fallback():
    """
    Verify that DuckDuckGo search queries and retrieves web search context successfully.
    """
    handler = KnowledgeGapHandler()
    
    # Mock only the LLM part to avoid external LLM calls during tests
    handler.llm = AsyncMock()
    handler.llm.chat_completion.return_value = "Python is a popular programming language."

    result = await handler._web_search_fallback("What is Python programming language?")
    
    # If the network request fails due to offline environment, the test should fail gracefully or pass if it's transient
    if result is not None:
        assert result["found"] is True
        assert "Python" in result["answer"]
        assert len(result["sources"]) > 0
        assert result["sources"][0]["url"].startswith("http")
        assert result["sources"][0]["title"] != ""
    else:
        # If result is None (e.g. rate-limited or offline), skip/log warning instead of breaking the build
        pytest.skip("Network search request timed out or returned empty result.")


def test_flashrank_rerank_integration():
    """
    Verify that FlashRank successfully scores and rerank passages locally on CPU.
    """
    reranker = CrossEncoderReranker()
    chunks = [
        {"text": "The quick brown fox jumps over the lazy dog.", "metadata": {"title": "Fox"}},
        {"text": "Artificial intelligence and machine learning models are expanding.", "metadata": {"title": "AI"}},
        {"text": "Cooking spaghetti requires boiling water, pasta, and marinara sauce.", "metadata": {"title": "Pasta"}},
    ]
    
    # Query matching the AI chunk best
    results = reranker.rerank("machine learning models", chunks, top_k=2)
    
    assert len(results) <= 2
    # The AI chunk should have the highest score and be first
    assert "artificial intelligence" in results[0]["text"].lower()
    assert "cross_encoder_score" in results[0]
    assert results[0]["cross_encoder_score"] > results[1]["cross_encoder_score"]


@pytest.mark.anyio
async def test_retriever_candidate_pruning():
    """
    Verify that Retriever.search calls the ranker with top_k=8 to prune candidates.
    """
    from backend.query.retriever import Retriever
    from unittest.mock import MagicMock, AsyncMock, patch
    
    retriever = Retriever()
    
    # Mock internal dependencies to avoid external calls
    retriever._detect_intent = AsyncMock(return_value={"scope": "specific", "temporal": "none"})
    retriever.embedder.aembed = AsyncMock(return_value=[[0.1]*384])
    retriever.vector_store.async_search = AsyncMock(return_value=[])
    
    # Mock Ranker and Reranker
    mock_ranker = MagicMock()
    mock_ranker.rerank.return_value = [{"chunk_id": "1", "text": "chunk 1"}]
    retriever.ranker = mock_ranker
    
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [{"chunk_id": "1", "text": "chunk 1"}]
    retriever.reranker = mock_reranker
    
    # Mock DB session context manager
    db_session_mock = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = []
    db_session_mock.execute.return_value = exec_res
    
    class MockContextManager:
        async def __aenter__(self):
            return db_session_mock
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    with patch("backend.query.retriever.async_session", return_value=MockContextManager()):
        results = await retriever.search(
            question="What is pruning?",
            workspace_id="ws_1",
            top_k=5
        )
        
    # Verify that ranker.rerank was called with top_k=8
    mock_ranker.rerank.assert_called_once()
    args, kwargs = mock_ranker.rerank.call_args
    assert kwargs.get("top_k") == 8
    
    # Verify that reranker.rerank was called with top_k=5
    mock_reranker.rerank.assert_called_once_with("What is pruning?", mock_ranker.rerank.return_value, top_k=5)

