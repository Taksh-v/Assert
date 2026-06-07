import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class PIIScrubber:
    """
    Cleans PII (Personally Identifiable Information) from text before indexing or prompting.
    Regex-based for MVP; can be upgraded to spaCy or Presidio.
    """

    # Basic regex patterns for PII
    PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
        "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    }

    def __init__(self, enabled_types: List[str] = None):
        self.enabled_types = enabled_types or list(self.PATTERNS.keys())

    def scrub(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Replace detected PII with placeholders and return the scrubbed text + list of detections.
        """
        scrubbed_text = text
        detections = []

        for pii_type in self.enabled_types:
            pattern = self.PATTERNS.get(pii_type)
            if not pattern:
                continue

            matches = list(re.finditer(pattern, scrubbed_text))
            # Process matches in reverse to keep indices valid after replacement
            for match in reversed(matches):
                start, end = match.span()
                val = match.group()
                placeholder = f"<{pii_type.upper()}>"
                
                scrubbed_text = scrubbed_text[:start] + placeholder + scrubbed_text[end:]
                
                detections.append({
                    "type": pii_type,
                    "original": val,
                    "start": start,
                    "end": end
                })

        return scrubbed_text, detections

    def scrub_batch(self, texts: List[str]) -> List[str]:
        return [self.scrub(t)[0] for t in texts]

if __name__ == "__main__":
    scrubber = PIIScrubber()
    sample = "Contact me at john.doe@example.com or 555-0199. My SSN is 123-45-6789."
    clean, matches = scrubber.scrub(sample)
    print(f"Original: {sample}")
    print(f"Scrubbed: {clean}")
    print(f"Matches: {matches}")
