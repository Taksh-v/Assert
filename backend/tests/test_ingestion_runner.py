import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.ingestion.runner import IngestionRunner
from backend.ingestion.document_store import VersionPlan
from backend.ingestion.document_run import IngestionPackage, IngestionState


class FakeTransformer:
    def __init__(self, name, recorder):
        self.name = name
        self.recorder = recorder

    async def transform(self, package: IngestionPackage):
        # mark order and add simple derived fields
        self.recorder.append(self.name)
        if self.name == "embedder":
            # simulate embeddings produced by embedder
            package.embeddings = [{"vec": [0.1, 0.2]} for _ in range(len(package.chunks) or 1)]
        if self.name == "chunker":
            package.chunks = ["chunkA", "chunkB"]


class FakeDocumentStore:
    def __init__(self):
        self.prepared = False
        self.persisted = None
        self.chunks = None

    async def prepare_version(self, raw_doc, workspace_id):
        self.prepared = True
        return VersionPlan(current_version=2, previous_document_id=None)

    async def persist_document(self, raw_doc, workspace_id, connector_id, doc_type, content_hash, chunk_count, tier, tags, version, previous_document_id):
        self.persisted = {"workspace_id": workspace_id, "version": version, "chunk_count": chunk_count}
        return SimpleNamespace(id="doc-123")

    async def persist_chunks(self, document_id, workspace_id, chunks, payloads, version):
        self.chunks = {"document_id": document_id, "chunks": chunks, "version": version}

    async def persist_events(self, workspace_id, document_id, events):
        return None


class FakeIndexAdapter:
    def __init__(self):
        self.upserted = None
        self.graph = None

    async def upsert_vectors(self, workspace_id, embeddings, payloads):
        self.upserted = {"workspace_id": workspace_id, "embeddings": embeddings, "payloads_len": len(payloads)}

    async def add_graph_artifacts(self, workspace_id, document_id, resolved_entities, events):
        self.graph = {"workspace_id": workspace_id, "document_id": document_id, "entities": resolved_entities, "events": events}

    def close(self):
        return None


@pytest.mark.asyncio
async def test_runner_transforms_persists_and_indexes():
    order = []
    transformers = [FakeTransformer("normalizer", order), FakeTransformer("chunker", order), FakeTransformer("embedder", order)]
    template = SimpleNamespace(transformers=transformers)

    raw_doc = SimpleNamespace(title="T", raw_content="x", source_url="u", source_type="web", tier=2, content_hash="h")

    store = FakeDocumentStore()
    index = FakeIndexAdapter()

    runner = IngestionRunner(document_store=store, index_adapter=index, default_template=template)

    package = await runner.process(raw_doc, "ws-1", "conn-1")

    assert order == ["normalizer", "chunker", "embedder"]
    assert store.prepared is True
    assert store.persisted["workspace_id"] == "ws-1"
    assert store.chunks["document_id"] == "doc-123"
    assert index.upserted is not None
    assert package.state == IngestionState.PERSISTED


@pytest.mark.asyncio
async def test_runner_respects_should_skip():
    class SkipStore(FakeDocumentStore):
        async def prepare_version(self, raw_doc, workspace_id):
            return VersionPlan(should_skip=True)

    transformers = [FakeTransformer("normalizer", [])]
    template = SimpleNamespace(transformers=transformers)

    raw_doc = SimpleNamespace(title="S", raw_content="y", source_url="u2", source_type="web", tier=2, content_hash="h2")

    store = SkipStore()
    index = FakeIndexAdapter()

    runner = IngestionRunner(document_store=store, index_adapter=index, default_template=template)
    package = await runner.process(raw_doc, "ws-2", None)

    assert package.state == IngestionState.PERSISTED
    assert store.persisted is None
    assert index.upserted is None


@pytest.mark.asyncio
async def test_runner_handles_transform_error_and_sets_failed():
    class BadTransformer:
        async def transform(self, package: IngestionPackage):
            raise RuntimeError("boom")

    template = SimpleNamespace(transformers=[BadTransformer()])
    raw_doc = SimpleNamespace(title="Bad", raw_content="z", source_url="u3", source_type="web", tier=2, content_hash="h3")

    store = FakeDocumentStore()
    index = FakeIndexAdapter()
    runner = IngestionRunner(document_store=store, index_adapter=index, default_template=template)

    package = IngestionPackage(raw_doc=raw_doc, workspace_id="ws-err")
    try:
        await runner.run(package)
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("Expected RuntimeError")

    assert package.state == IngestionState.FAILED
