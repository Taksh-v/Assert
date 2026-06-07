import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.ingestion.pipeline_v2 import (
    NormalizerTransformer,
    ParserTransformer,
    ScrubberTransformer,
    ClassifierTransformer,
    ChunkerTransformer,
    EmbedderTransformer,
    ExtractorTransformer
)

class FakeNormalizer:
    def normalize_generic(self, raw_data, workspace_id):
        return SimpleNamespace(
            title=raw_data.get("title", "Untitled"),
            raw_content=raw_data.get("content", "")
        )

@pytest.fixture
def package():
    raw_doc = {"title": "Raw Title", "content": "Raw Content"}
    return IngestionPackage(raw_doc=raw_doc, workspace_id="ws-1")

@pytest.mark.asyncio
async def test_normalizer_transformer(package):
    transformer = NormalizerTransformer(normalizer=FakeNormalizer())
    await transformer.transform(package)
    
    assert package.state == IngestionState.NORMALIZED
    assert package.title == "Raw Title"
    assert package.content == "Raw Content"

@pytest.mark.asyncio
async def test_parser_transformer(package):
    # Use bytes to trigger parse_bytes in ParserTransformer
    package.set_normalized("Title", b"Content", {})
    
    mock_parser = AsyncMock()
    mock_parser.parse_bytes.return_value = [{"type": "text", "content": "Parsed Content", "metadata": {}}]
    
    transformer = ParserTransformer(parser=mock_parser)
    await transformer.transform(package)
    
    assert package.state == IngestionState.PARSED
    assert len(package.elements) == 1
    assert package.elements[0]["content"] == "Parsed Content"

@pytest.mark.asyncio
async def test_scrubber_transformer(package):
    package.set_elements([{"type": "text", "content": "Sensitive Content", "metadata": {}}])
    
    mock_scrubber = MagicMock()
    mock_scrubber.scrub.return_value = ("Scrubbed Content", ["PII"])
    
    transformer = ScrubberTransformer(scrubber=mock_scrubber)
    await transformer.transform(package)
    
    assert package.state == IngestionState.SCRUBBED
    assert package.elements[0]["content"] == "Scrubbed Content"

@pytest.mark.asyncio
async def test_classifier_transformer(package):
    package.set_scrubbed([{"type": "text", "content": "Some Content", "metadata": {}}])
    
    mock_classifier = AsyncMock()
    mock_classifier.classify.return_value = "policy"
    
    transformer = ClassifierTransformer(classifier=mock_classifier)
    await transformer.transform(package)
    
    assert package.state == IngestionState.ENRICHED
    assert package.metadata["document_type"] == "policy"

@pytest.mark.asyncio
async def test_extractor_transformer(package):
    package.set_scrubbed([{"type": "text", "content": "Some Content", "metadata": {}}])
    
    mock_extractor = AsyncMock()
    mock_extractor.extract_semantic_metadata.return_value = {
        "entities": [{"name": "E1"}],
        "summary": "This is a summary"
    }
    
    mock_scrubber = MagicMock()
    mock_scrubber.scrub.return_value = ("Scrubbed Summary", [])
    
    transformer = ExtractorTransformer(extractor=mock_extractor, scrubber=mock_scrubber)
    await transformer.transform(package)
    
    assert package.state == IngestionState.ENRICHED
    assert package.metadata["summary"] == "Scrubbed Summary"
    assert package.metadata["entities"] == [{"name": "E1"}]

@pytest.mark.asyncio
async def test_chunker_transformer(package):
    package.set_enriched({"document_type": "policy"})
    package.set_elements([{"type": "text", "content": "Some Content", "metadata": {}}])
    
    mock_chunker = MagicMock()
    mock_chunker.chunk_elements.return_value = [{"content": "Chunk 1"}]
    
    transformer = ChunkerTransformer(chunker=mock_chunker)
    await transformer.transform(package)
    
    assert package.state == IngestionState.CHUNKED
    assert package.chunks == ["Chunk 1"]

@pytest.mark.asyncio
async def test_embedder_transformer(package):
    package.title = "Title"
    package.state = IngestionState.ENRICHED
    package.set_chunks(["Chunk 1"])
    package.metadata["summary"] = "Summary"
    
    mock_embedder = AsyncMock()
    mock_embedder.aembed_multi.return_value = [{"content": [0.1, 0.2]}]
    
    transformer = EmbedderTransformer(embedder=mock_embedder)
    await transformer.transform(package)
    
    assert package.embeddings == [{"content": [0.1, 0.2]}]
    mock_embedder.aembed_multi.assert_called_once_with(
        chunks=["Chunk 1"],
        title="Title",
        summary="Summary"
    )
