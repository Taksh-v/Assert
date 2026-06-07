import sys
from unittest.mock import MagicMock
sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

import pytest

# Save the real SharedLLMClient.chat_completion BEFORE any test file is imported.
# test_supervisor_routing.py replaces it at module-level, which runs during collection.
# Saving here (conftest is always imported first) lets us restore the original per-test.
try:
    from backend.core.llm_impl import SharedLLMClient as _SharedLLMClient
    _REAL_CHAT_COMPLETION = _SharedLLMClient.__dict__.get("chat_completion")
except Exception:
    _REAL_CHAT_COMPLETION = None


_MOCK_CHAT_COMPLETION = None


def pytest_collection_finish(session):
    global _MOCK_CHAT_COMPLETION
    try:
        from backend.core.llm_impl import SharedLLMClient
        _MOCK_CHAT_COMPLETION = SharedLLMClient.chat_completion
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _restore_shared_llm_client(request):
    """Restore SharedLLMClient.chat_completion before each test.
    
    test_supervisor_routing.py replaces it at module import time with an 
    AsyncMock(side_effect=Exception("Mock offline error")).
    """
    if "test_supervisor_routing" in request.node.nodeid:
        if _MOCK_CHAT_COMPLETION is not None:
            _SharedLLMClient.chat_completion = _MOCK_CHAT_COMPLETION
        yield
        return

    if _REAL_CHAT_COMPLETION is not None:
        _SharedLLMClient.chat_completion = _REAL_CHAT_COMPLETION
    yield
    if _REAL_CHAT_COMPLETION is not None:
        _SharedLLMClient.chat_completion = _REAL_CHAT_COMPLETION


from backend.agents.harness import TestHarness
import os

# If tests request in-memory Qdrant, inject the dummy client to avoid network calls.
if os.environ.get("QDRANT_MODE", "") == "memory":
    try:
        from backend.tests.fixtures.deterministic_adapters import DummyQdrantClient, NullGraphIndex
        import backend.core.vector_store as vs
        vs._GLOBAL_QDRANT_CLIENT = DummyQdrantClient()
        # Inject a null graph index where appropriate — some tests import GraphIndex/GraphStore
        # We set an attribute for callers to use when constructing graph adapters in tests.
        import backend.graph.graph_store as gs
        gs._TEST_NULL_GRAPH = NullGraphIndex()
    except Exception:
        pass


class NoopVectorStore:
    name = "vector"

    def run(self, inputs):
        # simple no-op response used by tests
        return {"status": "ok", "count": 0}


class NoopGraphStore:
    name = "graph"

    def run(self, inputs):
        return {"status": "ok"}


class MockDocumentStore:
    name = "document"

    def run(self, inputs):
        # simulate persisting a document bundle
        return {"status": "persisted", "id": inputs.get("id")}


@pytest.fixture
def noop_vector_store():
    return NoopVectorStore()


@pytest.fixture
def noop_graph_store():
    return NoopGraphStore()


@pytest.fixture
def mock_document_store():
    return MockDocumentStore()


@pytest.fixture
def harness_with_noops(noop_vector_store, noop_graph_store, mock_document_store):
    harness = TestHarness()
    harness.register_tool(noop_vector_store)
    harness.register_tool(noop_graph_store)
    harness.register_tool(mock_document_store)
    return harness
import os


os.environ.setdefault("USE_NATIVE_ORCHESTRATION", "true")

# Import offline ingestion mocks fixture so pytest can discover it
try:
    from backend.tests.fixtures.offline_ingestion_mocks import offline_ingestion_mocks  # noqa: F401
except Exception:
    try:
        # Fallback to relative import when run as a package
        from .fixtures.offline_ingestion_mocks import offline_ingestion_mocks  # noqa: F401
    except Exception:
        pass


import sys
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _ensure_common_external_mocks(monkeypatch):
    """Autouse fixture to ensure optional heavy external modules are mocked.

    This keeps individual tests simple and avoids module-level `sys.modules` edits.
    """
    # Minimal CryptContext shim
    class _MockCryptContext:
        def __init__(self, *args, **kwargs):
            pass

        def verify(self, plain, hashed):
            return True

        def hash(self, password):
            return "hashed"

    if "passlib" not in sys.modules:
        mock_passlib = MagicMock()
        mock_passlib.context = MagicMock()
        mock_passlib.context.CryptContext = _MockCryptContext
        monkeypatch.setitem(sys.modules, "passlib", mock_passlib)
        monkeypatch.setitem(sys.modules, "passlib.context", mock_passlib.context)

    for mod in ("groq", "sentence_transformers", "presidio_analyzer", "presidio_anonymizer"):
        if mod not in sys.modules:
            monkeypatch.setitem(sys.modules, mod, MagicMock())

    yield
