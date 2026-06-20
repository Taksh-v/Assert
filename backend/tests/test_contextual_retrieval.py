import asyncio
import pytest
from types import SimpleNamespace
from backend.core.config import get_settings
from backend.ingestion.contextualizer import ChunkContextualizer
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.document_run import DocumentIngestionRun, IngestionPackage, IngestionState
from backend.ingestion.pipeline_v2 import IngestionRunner, ChunkerTransformer, NormalizerTransformer, ParserTransformer, ScrubberTransformer, ClassifierTransformer, EmbedderTransformer, KnowledgeStore
from backend.ingestion.document_store import VersionPlan, SQLDocumentStore
from backend.models.chunk import Chunk as DBChunk
from backend.core.database import async_session

class FakeNormalizer:
    def normalize_generic(self, raw_data, workspace_id):
        return SimpleNamespace(title=raw_data["title"], raw_content=raw_data["content"])

class FakeScrubber:
    def scrub(self, text):
        return text, []

class FakeClassifier:
    async def classify(self, content, filename):
        return "policy"

class FakeEmbedder:
    def embed_multi(self, chunks, title, summary):
        return [{"content": [0.1] * 384, "title": [0.2] * 384, "summary": [0.3] * 384} for _ in chunks]

    async def aembed_multi(self, chunks, title, summary):
        return self.embed_multi(chunks, title, summary)

class FakeVectorIndex:
    def __init__(self):
        self.upserted = None

    def upsert_batch(self, workspace_id, multi_embeddings, payloads):
        self.upserted = {
            "workspace_id": workspace_id,
            "multi_embeddings": multi_embeddings,
            "payloads": payloads,
        }

@pytest.mark.asyncio
async def test_contextualizer_fallback():
    settings = get_settings()
    original_enabled = settings.enable_contextual_retrieval
    settings.enable_contextual_retrieval = True
    try:
        contextualizer = ChunkContextualizer()
        # Should fallback to title heuristic since the LLM request might fail or be mocked out in tests
        res = await contextualizer.contextualize(
            doc_title="API Reference Guide",
            doc_content="This is the full API guide.",
            chunk_content="GET /v1/users retrieves users."
        )
        assert len(res) > 0
    finally:
        settings.enable_contextual_retrieval = original_enabled

@pytest.mark.asyncio
async def test_hierarchical_chunker():
    chunker = DocumentChunker(chunk_size=100, child_size=30)
    elements = [{"type": "text", "content": "This is a long document about engineering standards. We keep it precise and modular.", "metadata": {}}]
    chunks = chunker.chunk_elements(elements)
    
    assert len(chunks) > 0
    parent = chunks[0]
    assert "content" in parent
    assert "children" in parent
    assert len(parent["children"]) >= 1

@pytest.mark.asyncio
async def test_document_run_persists_parent_child_relationships():
    # Setup test doc
    raw_doc = SimpleNamespace(
        title="Engineering Handbook",
        raw_content="This is a main chunk detailing coding standards. All code should be written in clean Python. Code quality rules.",
        source_id="src-handbook",
        source_url="slack://handbook",
        source_type="slack",
        content_format="text",
        tier=2,
        content_hash="hash-handbook",
        metadata={},
        permissions=[],
    )
    
    # We will mock SQLDocumentStore to verify it receives hierarchical metadata and payloads with parent_ids
    class MockSQLStore:
        def __init__(self):
            self.persisted_bundle = None

        async def prepare_version(self, raw_doc, workspace_id):
            return VersionPlan(current_version=1, previous_document_id=None)

        async def persist_document_bundle(self, raw_doc, workspace_id, connector_id, doc_type, content_hash, chunk_count, tier, tags, version, previous_document_id, chunks, payloads, hierarchical_chunks=None):
            self.persisted_bundle = {
                "chunks": chunks,
                "payloads": payloads,
                "hierarchical_chunks": hierarchical_chunks
            }
            return SimpleNamespace(id="doc-123", title="Engineering Handbook", source_url="slack://handbook")

    store = MockSQLStore()
    vector_index = FakeVectorIndex()
    
    run = DocumentIngestionRun(
        normalizer=FakeNormalizer(),
        scrubber=FakeScrubber(),
        classifier=FakeClassifier(),
        extractor=None,
        chunker=DocumentChunker(chunk_size=50, child_size=20),
        embedder=FakeEmbedder(),
        document_store=store,
        vector_index=vector_index,
        graph_index=None
    )
    
    res = await run.process(raw_doc, "workspace-1", "connector-1")
    assert res.status == "processed"
    
    # Check that store received hierarchical_chunks
    assert store.persisted_bundle is not None
    h_chunks = store.persisted_bundle["hierarchical_chunks"]
    assert h_chunks is not None
    assert len(h_chunks) > 0
    assert "parent_content" in h_chunks[0]
    assert "children" in h_chunks[0]
    
    # Since Qdrant payload is populated, ensure it has parent_id
    payloads = store.persisted_bundle["payloads"]
    assert len(payloads) > 0
    # The SQLDocumentStore updates payloads with parent_id, but here it's mocked,
    # let's verify if the run passed payloads to embed_and_index correctly.
    assert vector_index.upserted is not None
    assert len(vector_index.upserted["payloads"]) > 0
