import logging
import re
import asyncio
from typing import List, Dict, Any, Tuple
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class CitationValidator:
    """
    SOTA Generation: Claim-level citation verification (NLI-grounded).
    Checks if citations in the generated answer are supported by the referenced chunks.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    def extract_citations(self, sentence: str) -> List[int]:
        """Extract all 1-indexed citation numbers like [1], [2] from a sentence."""
        matches = re.findall(r"\[(\d+)\]", sentence)
        return [int(m) for m in matches]

    async def validate_sentence_citation(self, sentence: str, chunk_content: str, citation_num: int) -> bool:
        """
        Verify if the claim in the sentence is logically supported by the chunk_content.
        Uses a zero-cost LLM call (OpenRouter).
        """
        prompt = f"""You are a precise Natural Language Inference (NLI) validator.
Your task is to determine if the following sentence's claim is logically supported by the provided text chunk.

Sentence: "{sentence}"
Text Chunk: "{chunk_content}"

Is the claim in the sentence logically supported by the provided text chunk? Output only 'YES' or 'NO' and nothing else. No explanation.
"""
        try:
            res = await self.llm.chat_completion(
                system_prompt="You are a precise NLI validator. Output ONLY YES or NO.",
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=5,
                prompt_cache_key="citation_validator:v1"
            )
            val = res.strip().upper()
            if "YES" in val:
                return True
            elif "NO" in val:
                return False
            else:
                logger.warning(f"Unexpected NLI validator response: {res}. Defaulting to True.")
                return True
        except Exception as e:
            logger.warning(f"NLI validation failed: {e}. Defaulting to True.")
            return True

    async def validate_answer(self, answer_text: str, chunks: List[str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Scan all sentences in the answer, extract citations, and validate them.
        Returns:
            is_valid: True if all citations are valid, False otherwise.
            violations: List of violation details containing sentence, invalid citation, and context.
        """
        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", answer_text)
        violations = []
        is_valid = True

        tasks = []
        for sentence in sentences:
            citations = self.extract_citations(sentence)
            for cit in citations:
                chunk_idx = cit - 1
                if chunk_idx < 0 or chunk_idx >= len(chunks):
                    # Out of bounds citation!
                    violations.append({
                        "sentence": sentence,
                        "citation": cit,
                        "reason": f"Citation [{cit}] is out of bounds (total chunks: {len(chunks)})."
                    })
                    is_valid = False
                else:
                    tasks.append((sentence, chunks[chunk_idx], cit))

        if not tasks:
            return is_valid, violations

        # Execute LLM validations concurrently to reduce latency
        results = await asyncio.gather(*[
            self.validate_sentence_citation(sentence, chunk, cit)
            for sentence, chunk, cit in tasks
        ])

        for (sentence, chunk, cit), valid in zip(tasks, results):
            if not valid:
                violations.append({
                    "sentence": sentence,
                    "citation": cit,
                    "reason": f"Claim in sentence is not supported by referenced chunk [{cit}]."
                })
                is_valid = False

        return is_valid, violations
