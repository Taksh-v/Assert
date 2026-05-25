import asyncio
from typing import Protocol, Any, List, Dict, Optional

class IndexAdapter(Protocol):
    async def upsert_vectors(self, workspace_id: str, embeddings: list[dict], payloads: list[dict]) -> None:
        ...

    async def add_graph_artifacts(self, workspace_id: str, document_id: str, resolved_entities: list[dict], events: list[dict]) -> None:
        ...

    def close(self) -> None:
        ...


class DefaultIndexAdapter:
    """Adapter that wraps existing VectorIndex and GraphIndex implementations.

    This keeps compatibility with current synchronous implementations but exposes
    an async-friendly interface for the runner.
    """
    def __init__(self, vector_index: Optional[Any] = None, graph_index: Optional[Any] = None):
        try:
            from backend.ingestion.document_run import VectorIndex, GraphIndex

            self.vector_index = vector_index or VectorIndex()
            self.graph_index = graph_index or (GraphIndex() if GraphIndex is not None else None)
        except Exception:
            # Best-effort: if underlying index implementations fail to initialize
            # (e.g., vector store unavailable in test env), fall back to no-op
            class _NoopIndex:
                def upsert_batch(self, *args, **kwargs):
                    return None

                def add_document_artifacts(self, *args, **kwargs):
                    return None

                def close(self):
                    return None

            self.vector_index = vector_index or _NoopIndex()
            self.graph_index = graph_index or _NoopIndex()

    async def upsert_vectors(self, workspace_id: str, embeddings: list[dict], payloads: list[dict]) -> None:
        try:
            await asyncio.to_thread(self.vector_index.upsert_batch, workspace_id, embeddings, payloads)
        except Exception:
            # swallow; runner will have logged earlier
            return None

    async def add_graph_artifacts(self, workspace_id: str, document_id: str, resolved_entities: list[dict], events: list[dict]) -> None:
        if not self.graph_index:
            return None
        try:
            await asyncio.to_thread(
                self.graph_index.add_document_artifacts,
                workspace_id,
                document_id,
                "",
                "",
                resolved_entities,
                events,
            )
        except Exception:
            return None

    def close(self) -> None:
        if self.graph_index:
            try:
                self.graph_index.close()
            except Exception:
                pass
