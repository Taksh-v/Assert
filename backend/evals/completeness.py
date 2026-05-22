"""
Completeness Scorer — Rule-based check for answer coverage.

Unlike LLM-graded scorers, this uses deterministic keyword coverage analysis
to check if the answer addresses all key aspects of the query.
"""
import logging
import re
from backend.evals.base_scorer import BaseScorer, ScorerResult

logger = logging.getLogger(__name__)

# Common stop words to exclude from keyword analysis
STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "about", "between", "how",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "then", "there", "here", "when", "where", "why", "how", "much",
    "many", "like", "also", "well", "back", "even", "still"
})


class CompletenessScorer(BaseScorer):
    """
    Rule-based scorer that checks if the answer covers all key aspects of the query.
    
    Extracts meaningful keywords from the query and checks their presence
    in the answer. Does NOT require an LLM call.
    """

    name = "completeness"
    description = "Checks if the answer covers all key aspects of the user's question"
    min_threshold = 0.4

    async def _evaluate(self, query: str, output: str, context: str) -> ScorerResult:
        if not query or not output:
            return ScorerResult(self.name, 0.0, "No query or output provided", False)

        # Extract key terms from the query
        query_terms = self._extract_key_terms(query)
        if not query_terms:
            return ScorerResult(self.name, 1.0, "No key terms to check", True)

        # Check coverage in the output
        output_lower = output.lower()
        covered = []
        missing = []

        for term in query_terms:
            if term.lower() in output_lower:
                covered.append(term)
            else:
                missing.append(term)

        coverage = len(covered) / len(query_terms)

        # Build reasoning
        reasoning_parts = [f"Coverage: {len(covered)}/{len(query_terms)} key terms addressed"]
        if missing:
            reasoning_parts.append(f"Missing: {', '.join(missing[:5])}")
        if covered:
            reasoning_parts.append(f"Covered: {', '.join(covered[:5])}")

        return ScorerResult(
            scorer_name=self.name,
            score=round(coverage, 3),
            reasoning=". ".join(reasoning_parts),
            passed=False  # Will be set by base class
        )

    def _extract_key_terms(self, query: str) -> list:
        """Extract meaningful keywords from the query."""
        # Tokenize and clean
        words = re.findall(r'\b[a-zA-Z]+\b', query)
        
        # Filter stop words and short words
        key_terms = [
            w for w in words
            if w.lower() not in STOP_WORDS and len(w) > 2
        ]

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in key_terms:
            lower = term.lower()
            if lower not in seen:
                seen.add(lower)
                unique_terms.append(term)

        return unique_terms
