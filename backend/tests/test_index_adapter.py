import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.ingestion.index_adapter import DefaultIndexAdapter


@pytest.mark.asyncio
async def test_default_index_adapter_uses_thread_for_vector_and_graph_calls():
    vector_index = MagicMock()
    graph_index = MagicMock()
    adapter = DefaultIndexAdapter(vector_index=vector_index, graph_index=graph_index)

    thread_calls = []

    async def fake_to_thread(func, *args, **kwargs):
        thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    vector_index.upsert_batch.return_value = None
    graph_index.add_document_artifacts.return_value = None

    with patch("backend.ingestion.index_adapter.asyncio.to_thread", new=fake_to_thread):
        await adapter.upsert_vectors("ws-1", [{"vec": [1.0]}], [{"title": "Doc"}])
        await adapter.add_graph_artifacts("ws-1", "doc-1", [{"name": "E"}], [{"type": "milestone"}])

    assert len(thread_calls) == 2
    assert thread_calls[0][0] == vector_index.upsert_batch
    assert thread_calls[1][0] == graph_index.add_document_artifacts
    vector_index.upsert_batch.assert_called_once()
    graph_index.add_document_artifacts.assert_called_once()
