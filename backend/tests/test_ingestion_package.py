import pytest
from backend.ingestion.document_run import IngestionPackage, IngestionState, IllegalStateTransition

def test_package_initial_state():
    package = IngestionPackage(
        raw_doc={"title": "Test"},
        workspace_id="ws-1"
    )
    assert package.state == IngestionState.RAW
    assert package.workspace_id == "ws-1"

def test_package_transition_to_normalized():
    package = IngestionPackage(raw_doc={"title": "Test"}, workspace_id="ws-1")
    
    package.set_normalized(
        title="Normalized Title",
        content="Clean Content",
        metadata={"key": "value"}
    )
    
    assert package.state == IngestionState.NORMALIZED
    assert package.title == "Normalized Title"
    assert package.content == "Clean Content"

def test_package_invalid_transition_raises_error():
    package = IngestionPackage(raw_doc={"title": "Test"}, workspace_id="ws-1")
    
    # Cannot chunk before normalization/parsing
    with pytest.raises(IllegalStateTransition):
        package.set_chunks(["chunk 1"])
