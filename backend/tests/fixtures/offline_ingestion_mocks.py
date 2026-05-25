import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def offline_ingestion_mocks(monkeypatch):
    """Provide deterministic, offline mocks for ingestion pipeline heavy dependencies.

    Sets `sys.modules` entries for optional external libs and patches pipeline classes
    to use local test doubles. Tests should request this fixture when they need the
    offline behaviour.
    """
    # passlib CryptContext shim
    class MockCryptContext:
        def __init__(self, *args, **kwargs):
            pass

        def verify(self, plain, hashed):
            return True

        def hash(self, password):
            return "hashed"

    mock_passlib = MagicMock()
    mock_passlib.context = MagicMock()
    mock_passlib.context.CryptContext = MockCryptContext
    monkeypatch.setitem(sys.modules, "passlib", mock_passlib)
    monkeypatch.setitem(sys.modules, "passlib.context", mock_passlib.context)

    # Lightweight stubs for optional heavy deps
    monkeypatch.setitem(sys.modules, "groq", MagicMock())
    monkeypatch.setitem(sys.modules, "sentence_transformers", MagicMock())
    monkeypatch.setitem(sys.modules, "presidio_analyzer", MagicMock())
    monkeypatch.setitem(sys.modules, "presidio_anonymizer", MagicMock())

    # Local pipeline test doubles
    class MockPIIScrubber:
        def scrub(self, text):
            return text, []

    class MockEmbedder:
        def embed_multi(self, chunks, title, summary):
            return [{"content": [0.0] * 384} for _ in chunks]

        async def aembed_multi(self, chunks, title, summary):
            return self.embed_multi(chunks, title, summary)

    class MockEntityExtractor:
        async def extract_semantic_metadata(self, text):
            return {"entities": [], "topics": [], "keywords": [], "summary": ""}

    class MockDocumentClassifier:
        async def classify(self, content, filename):
            return "general"

    # Patch pipeline module classes
    import backend.ingestion.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIIScrubber", MockPIIScrubber, raising=False)
    monkeypatch.setattr(pipeline_mod, "Embedder", MockEmbedder, raising=False)
    monkeypatch.setattr(pipeline_mod, "EntityExtractor", MockEntityExtractor, raising=False)
    monkeypatch.setattr(pipeline_mod, "DocumentClassifier", MockDocumentClassifier, raising=False)

    # Patch corresponding implementation modules too
    import backend.ingestion.embedder as embed_mod
    monkeypatch.setattr(embed_mod, "Embedder", MockEmbedder, raising=False)
    import backend.ingestion.extractor as ext_mod
    monkeypatch.setattr(ext_mod, "EntityExtractor", MockEntityExtractor, raising=False)
    import backend.ingestion.classifier as clf_mod
    monkeypatch.setattr(clf_mod, "DocumentClassifier", MockDocumentClassifier, raising=False)

    yield
