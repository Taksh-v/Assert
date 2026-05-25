import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.ingestion.pipeline_v2 import (
    IngestionRunner,
    PipelineTemplate,
    KnowledgeStore,
    DefaultTemplate,
    PDFTemplate
)

class MockTransformer:
    def __init__(self, name):
        self.name = name
        self.called = False

    async def transform(self, package: IngestionPackage) -> None:
        self.called = True
        package.metadata[self.name] = True

@pytest.fixture
def mock_knowledge_store():
    store = MagicMock(spec=KnowledgeStore)
    store.persist = AsyncMock()
    return store

@pytest.mark.asyncio
async def test_runner_selects_template_by_metadata(mock_knowledge_store):
    default_template = PipelineTemplate(transformers=[MockTransformer("default")])
    custom_template = PipelineTemplate(transformers=[MockTransformer("custom")])
    
    runner = IngestionRunner(
        knowledge_store=mock_knowledge_store,
        templates={"policy": custom_template},
        default_template=default_template
    )
    
    # Selection by metadata
    package = IngestionPackage(raw_doc=MagicMock(), workspace_id="ws-1")
    package.metadata["document_type"] = "policy"
    
    template = runner.select_template(package)
    assert template == custom_template

@pytest.mark.asyncio
async def test_runner_selects_template_by_source_type(mock_knowledge_store):
    custom_template = PipelineTemplate(transformers=[MockTransformer("custom")])
    runner = IngestionRunner(
        knowledge_store=mock_knowledge_store,
        templates={"slack": custom_template}
    )
    
    raw_doc = SimpleNamespace(source_type="slack", source_url="")
    package = IngestionPackage(raw_doc=raw_doc, workspace_id="ws-1")
    
    template = runner.select_template(package)
    assert template == custom_template

@pytest.mark.asyncio
async def test_runner_selects_template_by_extension(mock_knowledge_store):
    pdf_template = PipelineTemplate(transformers=[MockTransformer("pdf")])
    runner = IngestionRunner(
        knowledge_store=mock_knowledge_store,
        templates={"pdf": pdf_template}
    )
    
    raw_doc = SimpleNamespace(source_type="generic", source_url="https://example.com/file.pdf")
    package = IngestionPackage(raw_doc=raw_doc, workspace_id="ws-1")
    
    template = runner.select_template(package)
    assert template == pdf_template

@pytest.mark.asyncio
async def test_runner_executes_pipeline(mock_knowledge_store):
    t1 = MockTransformer("t1")
    t2 = MockTransformer("t2")
    template = PipelineTemplate(transformers=[t1, t2])
    
    runner = IngestionRunner(
        knowledge_store=mock_knowledge_store,
        default_template=template
    )
    
    package = IngestionPackage(raw_doc=MagicMock(), workspace_id="ws-1")
    await runner.run(package)
    
    assert t1.called
    assert t2.called
    assert package.metadata["t1"] is True
    assert package.metadata["t2"] is True
    mock_knowledge_store.persist.assert_called_once_with(package)

@pytest.mark.asyncio
async def test_runner_handles_failure(mock_knowledge_store):
    class FailingTransformer:
        async def transform(self, package):
            raise ValueError("Boom")
            
    template = PipelineTemplate(transformers=[FailingTransformer()])
    runner = IngestionRunner(
        knowledge_store=mock_knowledge_store,
        default_template=template
    )
    
    package = IngestionPackage(raw_doc=MagicMock(), workspace_id="ws-1")
    
    with pytest.raises(ValueError, match="Boom"):
        await runner.run(package)
    
    assert package.state == IngestionState.FAILED
    mock_knowledge_store.persist.assert_not_called()

@pytest.mark.asyncio
async def test_default_template_structure():
    template = DefaultTemplate(
        normalizer=MagicMock(),
        parser=MagicMock(),
        scrubber=MagicMock(),
        classifier=MagicMock(),
        chunker=MagicMock(),
        embedder=MagicMock(),
        extractor=MagicMock()
    )
    assert len(template.transformers) == 7

@pytest.mark.asyncio
async def test_pdf_template_structure():
    template = PDFTemplate(
        normalizer=MagicMock(),
        parser=MagicMock(),
        scrubber=MagicMock(),
        classifier=MagicMock(),
        chunker=MagicMock(),
        embedder=MagicMock(),
        extractor=None
    )
    assert len(template.transformers) == 6
