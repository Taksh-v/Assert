import logging
from typing import Optional

from backend.ingestion.runner import IngestionRunner
from backend.ingestion.document_store import SQLDocumentStore
from backend.ingestion.index_adapter import DefaultIndexAdapter
from backend.ingestion.pipeline_v2 import DefaultTemplate

# Component imports
from backend.ingestion.normalizer import DocumentNormalizer
from backend.ingestion.document_parser import HybridParser
from backend.ingestion.pii_scrubber import PIIScrubber
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.embedder import Embedder
from backend.ingestion.extractor import EntityExtractor
from backend.ingestion.classifier import DocumentClassifier

logger = logging.getLogger(__name__)

class IngestionPipelineFactory:
    """
    Factory for creating fully configured IngestionRunner instances.
    Centralizes the initialization of all NLP and vector components,
    decoupling the worker concurrency tier from infrastructure details.
    """
    
    @classmethod
    def create_runner(cls) -> IngestionRunner:
        normalizer = DocumentNormalizer()
        parser = HybridParser()
        scrubber = PIIScrubber()
        embedder = Embedder()
        chunker = DocumentChunker()
        classifier = DocumentClassifier()
        
        try:
            extractor = EntityExtractor()
        except Exception as e:
            logger.warning(f"EntityExtractor init failed (non-fatal): {e}")
            extractor = None

        document_store = SQLDocumentStore()
        index_adapter = DefaultIndexAdapter()
        
        return IngestionRunner(
            document_store=document_store,
            index_adapter=index_adapter,
            default_template=DefaultTemplate(
                normalizer=normalizer,
                parser=parser,
                scrubber=scrubber,
                classifier=classifier,
                chunker=chunker,
                embedder=embedder,
                extractor=extractor,
            )
        )
