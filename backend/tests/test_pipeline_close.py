from backend.ingestion.pipeline import IngestionPipeline


class FakeDocumentRun:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_pipeline_close_delegates_to_document_run_close():
    pipeline = IngestionPipeline()
    fake = FakeDocumentRun()
    pipeline.document_run = fake
    pipeline.close()
    assert fake.closed is True
