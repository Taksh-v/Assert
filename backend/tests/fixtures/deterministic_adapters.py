"""Deterministic test adapters for CI and unit tests.

Provide simple no-op or in-memory adapters for external systems so tests
can run without network dependencies and with deterministic outputs.
"""

class NullSanitizer:
    """A sanitizer that returns the input unchanged."""

    def sanitize(self, text: str) -> str:
        return text


class DummyQdrantClient:
    """A tiny in-memory stand-in for Qdrant used by tests.

    This implements only the minimal interface used by tests: `upsert` and `search`.
    Not meant as a full replacement; just enough for deterministic unit tests.
    """

    def __init__(self):
        self.points = []

    def upsert(self, collection_name: str, points):
        # store points as-is
        self.points.extend(points)
        return {"status": "ok", "upserted": len(points)}

    def search(self, collection_name: str, query_vector, top: int = 10):
        # naive: return first `top` points
        return self.points[:top]


class NullGraphIndex:
    """No-op graph index used in tests to avoid external graph calls."""

    def write_nodes(self, nodes):
        return True

    def write_edges(self, edges):
        return True
