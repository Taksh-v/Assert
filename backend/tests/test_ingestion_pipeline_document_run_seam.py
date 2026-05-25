def test_connector_sync_does_not_expose_legacy_document_processing_seam():
    from backend.ingestion.pipeline import IngestionPipeline

    assert not hasattr(IngestionPipeline, "_process_document")
