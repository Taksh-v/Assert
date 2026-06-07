"""Simple ingestion harness to run concurrent IngestionRunner tasks and print per-stage timings.

Run with: PYTHONPATH=. python backend/tools/ingestion_harness.py
"""
import asyncio
import random
import logging
from types import SimpleNamespace

from backend.ingestion.runner import IngestionRunner
from backend.ingestion.document_run import IngestionPackage
from backend.ingestion.document_store import VersionPlan
from backend.ingestion.metrics import timer
from backend.ingestion.embedder import Embedder

logger = logging.getLogger("ingestion_harness")


class SimpleTransformer:
    def __init__(self, name, func):
        self.name = name
        self.func = func

    async def transform(self, package: IngestionPackage):
        await self.func(package)


class Chunker:
    async def transform(self, package: IngestionPackage):
        text = getattr(package.raw_doc, "raw_content", "")
        # naive split into 200-char chunks
        package.chunks = [text[i:i+200] for i in range(0, len(text), 200)]


class EmbedderTransformer:
    def __init__(self):
        self.embedder = Embedder()

    async def transform(self, package: IngestionPackage):
        if not package.chunks:
            package.chunks = [getattr(package.raw_doc, "raw_content", "")]
        vectors = await self.embedder.aembed_multi(package.chunks, getattr(package.raw_doc, "title", ""), package.metadata.get("summary", ""))
        # `aembed_multi` returns list of dicts with named vectors; normalize to embeddings list
        package.embeddings = vectors


class InMemoryDocumentStore:
    def __init__(self):
        self.docs = {}
        self.chunks = {}

    async def prepare_version(self, raw_doc, workspace_id):
        return VersionPlan(current_version=1, previous_document_id=None)

    async def persist_document(self, raw_doc, workspace_id, connector_id, doc_type, content_hash, chunk_count, tier, tags, version, previous_document_id):
        doc_id = f"doc-{random.randint(1000,9999)}"
        self.docs[doc_id] = {"workspace_id": workspace_id, "title": getattr(raw_doc, "title", ""), "version": version}
        return SimpleNamespace(id=doc_id)

    async def persist_chunks(self, document_id, workspace_id, chunks, payloads, version):
        self.chunks[document_id] = {"chunks": chunks, "payloads_len": len(payloads)}

    async def persist_events(self, workspace_id, document_id, events):
        return None


class NoopIndexAdapter:
    async def upsert_vectors(self, workspace_id, embeddings, payloads):
        # simulate small network delay
        await asyncio.sleep(0.01)

    async def add_graph_artifacts(self, workspace_id, document_id, resolved_entities, events):
        await asyncio.sleep(0.005)

    def close(self):
        return None


async def run_one(runner: IngestionRunner, doc_idx: int):
    raw = SimpleNamespace(title=f"doc-{doc_idx}", raw_content=("Lorem ipsum " * 100), source_url=f"u{doc_idx}", source_type="web", tier=2, content_hash=f"h{doc_idx}")
    package = await runner.process(raw, workspace_id="ws-harness")
    return package


async def main(concurrency: int = 5):
    store = InMemoryDocumentStore()
    index = NoopIndexAdapter()
    transformers = [Chunker(), EmbedderTransformer()]
    template = SimpleNamespace(transformers=transformers)

    runner = IngestionRunner(document_store=store, index_adapter=index, default_template=template)

    tasks = [run_one(runner, i) for i in range(concurrency)]

    with timer("harness.batch_run"):
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Summarize
    succeeded = 0
    failed = 0
    for r in results:
        if isinstance(r, Exception):
            failed += 1
        elif getattr(r, "state", None) is None:
            failed += 1
        else:
            succeeded += 1

    print(f"Harness complete: {succeeded} succeeded, {failed} failed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--concurrency", type=int, default=5)
    args = parser.parse_args()

    asyncio.run(main(concurrency=args.concurrency))
