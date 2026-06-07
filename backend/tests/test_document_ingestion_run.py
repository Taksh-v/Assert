import asyncio
from types import SimpleNamespace

from backend.ingestion.document_run import DocumentIngestionError, DocumentIngestionRun
from backend.ingestion.document_store import VersionPlan


class FakeNormalizer:
    def normalize_generic(self, raw_data, workspace_id):
        return SimpleNamespace(title=raw_data["title"], raw_content=raw_data["content"])


class FakeScrubber:
    def scrub(self, text):
        return text.replace("secret", "[redacted]"), []


class FakeClassifier:
    async def classify(self, content, filename):
        return "policy"


class FakeExtractor:
    async def extract_semantic_metadata(self, text):
        return {
            "entities": [],
            "topics": [],
            "keywords": ["handbook"],
            "summary": "A clean summary",
            "events": [],
        }


class FakeChunker:
    def chunk_elements(self, elements, doc_type="auto"):
        text = elements[0]["content"]
        return [{"content": text[:12]}, {"content": text[12:]}]


class FakeEmbedder:
    def embed_multi(self, chunks, title, summary):
        return [
            {"content": [0.1], "title": [0.2], "summary": [0.3]}
            for _ in chunks
        ]


class FakeDocumentStore:
    def __init__(self):
        self.persisted_document = None
        self.persisted_chunks = None

    async def prepare_version(self, raw_doc, workspace_id):
        return VersionPlan(current_version=3, previous_document_id="old-doc-id")

    async def persist_document(
        self,
        raw_doc,
        workspace_id,
        connector_id,
        doc_type,
        content_hash,
        chunk_count,
        tier,
        tags,
        version,
        previous_document_id,
    ):
        self.persisted_document = {
            "workspace_id": workspace_id,
            "connector_id": connector_id,
            "doc_type": doc_type,
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "tier": tier,
            "tags": tags,
            "version": version,
            "previous_document_id": previous_document_id,
        }
        return SimpleNamespace(id="new-doc-id")

    async def persist_chunks(self, document_id, workspace_id, chunks, payloads, version):
        self.persisted_chunks = {
            "document_id": document_id,
            "workspace_id": workspace_id,
            "chunks": chunks,
            "payloads": payloads,
            "version": version,
        }

    async def persist_events(self, workspace_id, document_id, events):
        return None


class FakeVectorIndex:
    def __init__(self):
        self.upserted = None

    def upsert_batch(self, workspace_id, multi_embeddings, payloads):
        self.upserted = {
            "workspace_id": workspace_id,
            "multi_embeddings": multi_embeddings,
            "payloads": payloads,
        }


class FakeGraphIndex:
    def add_document_artifacts(self, **kwargs):
        return None

    def close(self):
        return None


async def _process_document():
    raw_doc = SimpleNamespace(
        title="Team Handbook",
        raw_content="secret leave policy",
        source_id="src-1",
        source_url="slack://handbook",
        source_type="slack",
        content_format="text",
        tier=2,
        content_hash="hash-1",
        metadata={},
        permissions=[],
    )
    document_store = FakeDocumentStore()
    vector_index = FakeVectorIndex()
    run = DocumentIngestionRun(
        normalizer=FakeNormalizer(),
        scrubber=FakeScrubber(),
        classifier=FakeClassifier(),
        extractor=FakeExtractor(),
        chunker=FakeChunker(),
        embedder=FakeEmbedder(),
        document_store=document_store,
        vector_index=vector_index,
        graph_index=FakeGraphIndex(),
    )

    result = await run.process(raw_doc, "workspace-1", "connector-1")

    assert result.status == "processed"
    assert result.document_id == "new-doc-id"
    assert result.version == 3
    assert result.chunk_count == 2
    assert document_store.persisted_document["doc_type"] == "policy"
    assert document_store.persisted_document["tags"] == ["handbook"]
    assert document_store.persisted_chunks["document_id"] == "new-doc-id"
    assert document_store.persisted_chunks["chunks"] == ["[redacted] l", "eave policy"]
    assert vector_index.upserted["workspace_id"] == "workspace-1"
    assert vector_index.upserted["payloads"][0]["version"] == 3


async def _wrap_document_error():
    raw_doc = SimpleNamespace(
        title="Broken",
        raw_content="content",
        source_id="src-2",
        source_url="slack://broken",
        source_type="slack",
        content_format="text",
        tier=2,
        content_hash="hash-2",
        metadata={},
        permissions=[],
    )

    class BrokenClassifier:
        async def classify(self, content, filename):
            raise RuntimeError("classification failed")

    run = DocumentIngestionRun(
        normalizer=FakeNormalizer(),
        scrubber=FakeScrubber(),
        classifier=BrokenClassifier(),
        extractor=None,
        chunker=FakeChunker(),
        embedder=FakeEmbedder(),
        document_store=FakeDocumentStore(),
        vector_index=FakeVectorIndex(),
        graph_index=FakeGraphIndex(),
    )

    try:
        await run.process(raw_doc, "workspace-1", "connector-1")
    except DocumentIngestionError as exc:
        assert "classification failed" in str(exc)
        assert exc.failure_snapshot["source_url"] == "slack://broken"
    else:
        raise AssertionError("Expected DocumentIngestionError")


def test_document_ingestion_run_processes_one_document():
    asyncio.run(_process_document())


def test_document_ingestion_run_wraps_failures():
    asyncio.run(_wrap_document_error())
