from __future__ import annotations

"""Orchestrator seam for ingestion.

This module defines the `IngestionOrchestrator` interface and simple adapter stubs.
The goal is to provide a single seam callers can depend on while we migrate
existing callers (ConnectorSyncRunner, workers) to use this interface.
"""

from dataclasses import dataclass
from typing import List, Protocol


@dataclass
class SemanticChunk:
    id: str
    text: str
    metadata: dict


@dataclass
class ExtractionContext:
    source_id: str
    run_id: str
    offsets: dict


class IngestionOrchestrator(Protocol):
    async def run(self, source: str) -> List[SemanticChunk]:
        """Run ingestion for a given source/document and return produced chunks."""


class LegacyIngestionOrchestrator:
    """Adapter around the legacy `IngestionPipeline` implementation.

    This adapter delegates to the existing `IngestionPipeline` runner to preserve
    current behaviour while callers migrate to the `IngestionOrchestrator` seam.
    """

    def __init__(self, pipeline=None):
        # Allow reusing an existing IngestionPipeline instance when provided
        if pipeline is not None:
            self.pipeline = pipeline
        else:
            # Lazy import to avoid heavy module init at import-time
            from backend.ingestion.pipeline import IngestionPipeline
            self.pipeline = IngestionPipeline()

    async def run(self, source: object) -> List[SemanticChunk]:
        """Run ingestion for a provided document-like object.

        `source` can be a connector document object (as returned by connector.fetch_documents)
        or a simple dict with at least `raw_content`/`content` and `workspace_id`/`connector_id`.
        The adapter will attempt to call the pipeline runner and return an empty list
        of `SemanticChunk` placeholders (full chunk materialization will be implemented
        in a later iteration behind the seam).
        """
        # Attempt to call the pipeline's runner.process if available
        try:
            runner = getattr(self.pipeline, "runner", None)
            if runner and hasattr(runner, "process"):
                # runner.process expects (doc_obj, workspace_id, connector_id)
                workspace_id = getattr(source, "workspace_id", None) or source.get("workspace_id") if isinstance(source, dict) else None
                connector_id = getattr(source, "connector_id", None) or source.get("connector_id") if isinstance(source, dict) else None
                # If we don't have workspace/connector, call process with None values
                await runner.process(source, workspace_id, connector_id)
                return []
        except Exception:
            # Preserve previous behavior: swallow and return empty list for now
            return []
        return []

    async def process(self, doc_obj: object, workspace_id: str, connector_id: str) -> None:
        """Process a single document using the underlying runner if available.

        This mirrors the `IngestionRunner.process` signature expected by callers.
        """
        runner = getattr(self.pipeline, "runner", None)
        if runner and hasattr(runner, "process"):
            # Allow exceptions to propagate so callers can record failures/telemetry
            await runner.process(doc_obj, workspace_id, connector_id)


class PilotIngestionOrchestrator:
    """Adapter for the pilot ConnectorSyncRunner-backed pipeline."""

    async def run(self, source: str) -> List[SemanticChunk]:
        """Delegate to the ConnectorSyncRunner when `source` is a sync_run_id.

        If `source` is not a sync_run_id, this method is a no-op for now.
        """
        try:
            from backend.workers.sync_runner import ConnectorSyncRunner
            runner = ConnectorSyncRunner()
            # We expect `source` to be a sync_run_id (str). The connector runner returns stats.
            await runner.run(source)
            return []
        except Exception:
            return []

    async def process(self, doc_obj: object, workspace_id: str, connector_id: str) -> None:
        """Process a single document by delegating to the pilot's IngestionRunner."""
        try:
            # Try to reuse a runner from ConnectorSyncRunner if available
            from backend.workers.sync_runner import ConnectorSyncRunner
            runner = ConnectorSyncRunner().runner
            if runner and hasattr(runner, "process"):
                await runner.process(doc_obj, workspace_id, connector_id)
        except Exception:
            # As a fallback, try to construct a temporary IngestionRunner similar to the pilot
            try:
                from backend.ingestion.runner import IngestionRunner
                from backend.ingestion.document_store import SQLDocumentStore
                from backend.ingestion.index_adapter import DefaultIndexAdapter
                from backend.ingestion.pipeline_v2 import DefaultTemplate
                from backend.ingestion.normalizer import DocumentNormalizer
                from backend.ingestion.document_parser import HybridParser
                from backend.ingestion.pii_scrubber import PIIScrubber
                from backend.ingestion.chunker import DocumentChunker
                from backend.ingestion.embedder import Embedder
                from backend.ingestion.extractor import EntityExtractor
                from backend.ingestion.classifier import DocumentClassifier

                normalizer = DocumentNormalizer()
                parser = HybridParser()
                scrubber = PIIScrubber()
                classifier = DocumentClassifier()
                chunker = DocumentChunker()
                embedder = Embedder()
                try:
                    extractor = EntityExtractor()
                except Exception:
                    extractor = None

                document_store = SQLDocumentStore()
                index_adapter = DefaultIndexAdapter()
                temp_runner = IngestionRunner(
                    document_store=document_store,
                    index_adapter=index_adapter,
                    default_template=DefaultTemplate(
                        normalizer=normalizer,
                        parser=parser,
                        scrubber=scrubber,
                        classifier=classifier,
                        chunker=chunker,
                        embedder=embedder,
                        extractor=extractor,
                    )
                )
                if hasattr(temp_runner, "process"):
                    await temp_runner.process(doc_obj, workspace_id, connector_id)
            except Exception:
                return
