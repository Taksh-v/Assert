import logging
from typing import List, Dict
from backend.core.config import get_settings
from backend.query.retriever import RetrievalResult

settings = get_settings()
logger = logging.getLogger(__name__)


class Answer:
    def __init__(self, answer_text: str, sources: List[Dict[str, str]], tokens_used: int = 0):
        self.answer_text = answer_text
        self.sources = sources
        self.tokens_used = tokens_used


class Generator:
    """
    Generates grounded answers from retrieved chunks using an LLM.
    """

    def __init__(self):
        self.model = settings.groq_model
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except TypeError as e:
            logger.warning(f"Groq client init failed (SDK version mismatch): {e}")
            self._client_init_failed = True
            return None
        except Exception as e:
            logger.warning(f"Groq client init failed: {e}")
            self._client_init_failed = True
            return None

    async def generate_answer(self, question: str, chunks: List[RetrievalResult]) -> Answer:
        """
        Generate answer based on retrieved chunks.
        """
        logger.info(f"Generating answer for: {question}")
        
        # 1. Construct context
        context = "\n\n".join([f"Source: {c.title} ({c.source_url})\nContent: {c.content}" for c in chunks])
        
        # 2. Define system prompt
        system_prompt = (
            "You are the Assest knowledge assistant. Answer ONLY based on the provided knowledge chunks. "
            "If the answer is not in the chunks, say 'I couldn't find this in your company's knowledge base'. "
            "Always cite the source document for each claim. Use Markdown formatting."
        )
        
        sources = []
        seen_sources = set()
        for chunk in chunks:
            key = (chunk.title, chunk.source_url)
            if key not in seen_sources:
                sources.append({"title": chunk.title, "url": chunk.source_url})
                seen_sources.add(key)

        if not self.client:
            best = chunks[0].content.strip() if chunks else ""
            fallback = best[:900] + ("..." if len(best) > 900 else "")
            return Answer(answer_text=fallback or "I couldn't find this in your company's knowledge base.", sources=sources)

        logger.info(f"Calling LLM ({self.model})...")
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Question: {question}\n\nKnowledge chunks:\n{context}"},
                ],
                model=self.model,
                temperature=0.1,
            )
            answer_text = response.choices[0].message.content or ""
            return Answer(answer_text=answer_text, sources=sources)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            best = chunks[0].content.strip() if chunks else ""
            return Answer(answer_text=best[:900] or "I couldn't find this in your company's knowledge base.", sources=sources)
