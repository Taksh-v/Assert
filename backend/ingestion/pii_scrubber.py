import logging
import json
import uuid
from typing import List, Dict, Any, Tuple
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)


class PIIScrubber:
    """
    Blueprint Layer 11: Security & Redaction.
    Scrubs PII and maintains a vault for authorized re-identification.
    """

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.vault: Dict[str, str] = {} # placeholder -> original
        self._add_custom_recognizers()

    def _add_custom_recognizers(self):
        """Add Indian ID recognizers."""
        pan_pattern = Pattern(name="pan_pattern", regex=r"[A-Z]{5}[0-9]{4}[A-Z]{1}", score=0.8)
        pan_recognizer = PatternRecognizer(supported_entity="PAN_CARD", patterns=[pan_pattern])
        self.analyzer.registry.add_recognizer(pan_recognizer)

        aadhaar_pattern = Pattern(name="aadhaar_pattern", regex=r"\d{4}\s\d{4}\s\d{4}", score=0.8)
        aadhaar_recognizer = PatternRecognizer(supported_entity="AADHAAR_CARD", patterns=[aadhaar_pattern])
        self.analyzer.registry.add_recognizer(aadhaar_recognizer)

    def scrub(self, text: str) -> Tuple[str, List[str]]:
        """
        Scrub PII from text and return the scrubbed text and list of found entity types.
        """
        if not text:
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
