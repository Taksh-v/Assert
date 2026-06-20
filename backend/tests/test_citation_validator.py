import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from backend.query.citation_validator import CitationValidator
from backend.models.chunk import Chunk as DBChunk
from backend.query.query_service import QueryService, Answer, ResponseTier

@pytest.mark.asyncio
async def test_citation_extraction():
    validator = CitationValidator()
    cits = validator.extract_citations("This statement is supported by chunk [1] and [2]. However, [3] says otherwise.")
    assert cits == [1, 2, 3]
    
    cits_none = validator.extract_citations("This statement has no citations.")
    assert cits_none == []

@pytest.mark.asyncio
async def test_citation_nli_validation_mocked():
    validator = CitationValidator()
    
    # Mock LLM chat completion
    async def mock_chat_completion(*args, **kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        if 'Sentence: "The system retrieves user records."' in user_prompt:
            return "YES"
        return "NO"
    
    validator.llm.chat_completion = mock_chat_completion
    
    res_true = await validator.validate_sentence_citation(
        sentence="The system retrieves user records.",
        chunk_content="GET /v1/users retrieves user records.",
        citation_num=1
    )
    assert res_true is True
    
    res_false = await validator.validate_sentence_citation(
        sentence="The system deletes user records.",
        chunk_content="GET /v1/users retrieves user records.",
        citation_num=1
    )
    assert res_false is False

@pytest.mark.asyncio
async def test_answer_validation():
    validator = CitationValidator()
    
    # Mock NLI validation
    async def mock_validate_sentence_citation(sentence, chunk, cit_num):
        if "deletes" in sentence:
            return False
        return True
    validator.validate_sentence_citation = mock_validate_sentence_citation
    
    chunks = [
        "GET /v1/users retrieves user records.",
        "POST /v1/users creates user records."
    ]
    
    answer_text = "The system retrieves user records [1]. However, it deletes records [2]."
    is_valid, violations = await validator.validate_answer(answer_text, chunks)
    
    assert is_valid is False
    assert len(violations) == 1
    assert violations[0]["citation"] == 2
    assert "deletes" in violations[0]["sentence"]

@pytest.mark.asyncio
async def test_query_service_critic_loop():
    db_mock = AsyncMock()
    db_res = MagicMock()
    db_res.scalar.return_value = None
    db_mock.execute.return_value = db_res
    query_service = QueryService(db=db_mock)
    
    # Mock generator to return initial flawed answer
    class MockGenerator:
        async def generate_grounded_response(self, *args, **kwargs):
            return Answer(
                answer_text="Startup statistics show high growth [1]. It also claims 90% fail in day 1 [2].",
                sources=[],
                grounding_score=0.9,
                response_tier=ResponseTier.FAST_RAG.value
            )
    query_service.generator = MockGenerator()
    
    # Mock LLM Client for rewriting response
    async def mock_chat_completion(*args, **kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        # If it's the citation corrector rewrite call, return corrected answer
        if "precise citation corrector" in user_prompt or "citation corrector" in kwargs.get("system_prompt", ""):
            return "Startup statistics show high growth [1]. It is well-known that most startups face major scaling challenges [2]."
        return "YES"
    query_service.llm.chat_completion = mock_chat_completion
    
    # Mock CitationValidator
    class MockValidator:
        async def validate_answer(self, answer_text, chunks):
            # First attempt fails on "90% fail" statement
            if "scaling challenges" not in answer_text:
                return False, [{
                    "sentence": "It also claims 90% fail in day 1 [2].",
                    "citation": 2,
                    "reason": "Not supported by Chunk 2."
                }]
            return True, []
            
    import backend.query.query_service as query_service_module
    original_validator_class = query_service_module.CitationValidator
    
    # Setup temporary mock class in module
    query_service_module.CitationValidator = lambda: MockValidator()
    
    # Mock verified context
    verified = SimpleNamespace(
        grounding_score=0.9,
        needs_web_fallback=False,
        verified_chunks=[
            SimpleNamespace(content="Startup statistics report high growth across sectors."),
            SimpleNamespace(content="Startups face major scaling challenges in their early stages.")
        ]
    )
    
    try:
        # We will mock the database session/QueryLog creation inside query_service to be a no-op
        query_service._should_run_quality_eval = lambda *args, **kwargs: False
        query_service.crag.verify = AsyncMock(return_value=verified)
        query_service.retriever.search = AsyncMock(return_value=[])
        
        answer = await query_service._fast_rag_path(
            question="startup growth?",
            workspace_id="workspace-1",
            user_id="user-1",
            history=[],
            context_files=None,
            user_role="employee"
        )
        
        assert "scaling challenges" in answer.answer_text
        assert "90% fail" not in answer.answer_text
        
    finally:
        query_service_module.CitationValidator = original_validator_class
