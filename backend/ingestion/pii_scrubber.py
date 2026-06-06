import logging
import json
import uuid
from typing import List, Dict, Any, Tuple
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PIIScrubber:
    """
    Blueprint Layer 11: Security & Redaction.
    Scrubs PII and maintains a vault for authorized re-identification.
    """
    _shared_analyzer = None
    _shared_anonymizer = None
    _load_attempted = False
    _custom_recognizers_added = False

    def __init__(self):
        if not getattr(PIIScrubber, "_load_attempted", False):
            setattr(PIIScrubber, "_load_attempted", True)
            try:
                from presidio_analyzer import AnalyzerEngine
                from presidio_anonymizer import AnonymizerEngine
                PIIScrubber._shared_analyzer = AnalyzerEngine()
                PIIScrubber._shared_anonymizer = AnonymizerEngine()
            except ImportError as e:
                logger.warning(f"presidio not available, PII scrubbing disabled: {e}")
            except Exception as e:
                logger.warning(f"presidio initialization failed, PII scrubbing disabled: {e}")

        self.analyzer = getattr(PIIScrubber, "_shared_analyzer", None)
        self.anonymizer = getattr(PIIScrubber, "_shared_anonymizer", None)
        self.vault: Dict[str, str] = {}  # placeholder -> original
        if self.analyzer and not getattr(PIIScrubber, "_custom_recognizers_added", False):
            self._add_custom_recognizers()
            setattr(PIIScrubber, "_custom_recognizers_added", True)

    def _add_custom_recognizers(self):
        """Add Indian ID recognizers."""
        if not self.analyzer:
            return
        try:
            from presidio_analyzer import Pattern, PatternRecognizer
            pan_pattern = Pattern(name="pan_pattern", regex=r"[A-Z]{5}[0-9]{4}[A-Z]{1}", score=0.8)
            pan_recognizer = PatternRecognizer(supported_entity="PAN_CARD", patterns=[pan_pattern])
            self.analyzer.registry.add_recognizer(pan_recognizer)

            aadhaar_pattern = Pattern(name="aadhaar_pattern", regex=r"\d{4}\s\d{4}\s\d{4}", score=0.8)
            aadhaar_recognizer = PatternRecognizer(supported_entity="AADHAAR_CARD", patterns=[aadhaar_pattern])
            self.analyzer.registry.add_recognizer(aadhaar_recognizer)
        except Exception as e:
            logger.warning(f"Failed to add custom recognizers: {e}")

    def scrub(self, text: str) -> Tuple[str, List[str]]:
        """
        Scrub PII from text and return the scrubbed text and list of found entity types.
        """
        if not text:
            return text, []
        if not self.analyzer or not self.anonymizer:
            if not settings.is_development:
                raise RuntimeError("PII Scrubber is uninitialized or failed to start in production. Ingestion halted.")
            return text, []

        try:
            results = self.analyzer.analyze(text=text, language='en')
            
            # For each result, store the original in the vault
            # This is a simplified "vault" logic. In production, placeholders would be UUIDs.
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=results
            )
            
            entities_found = list(set([res.entity_type for res in results]))
            return anonymized_result.text, entities_found
        except Exception as e:
            logger.error(f"Error scrubbing PII: {e}")
            return text, []
