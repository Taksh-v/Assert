import pytest
from types import SimpleNamespace
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.ingestion.pipeline_v2 import NormalizerTransformer

class FakeNormalizer:
    def normalize_generic(self, raw_data, workspace_id):
        return SimpleNamespace(
            title=raw_data.get("title", "Untitled"),
            raw_content=raw_data.get("content", "")
        )

@pytest.mark.asyncio
async def test_normalizer_transformer_updates_package():
    raw_doc = {"title": "Raw Title", "content": "Raw Content"}
    package = IngestionPackage(raw_doc=raw_doc, workspace_id="ws-1")
    
    transformer = NormalizerTransformer(normalizer=FakeNormalizer())
    await transformer.transform(package)
    
    assert package.state == IngestionState.NORMALIZED
    assert package.title == "Raw Title"
    assert package.content == "Raw Content"
