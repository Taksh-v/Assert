import pytest
import json
import re
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from backend.main import ValueAlignmentMiddleware
from backend.reasoning.agents.researcher import ResearcherAgent
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.query.retriever import RetrievalResult
from backend.query.resolution import VerifiedContext, VerifiedChunk, CRAGVerdict
from backend.reasoning.state import ReasoningState

# ─────────────────────────────────────────────────────────
# 1. Test ValueAlignmentMiddleware
# ─────────────────────────────────────────────────────────

def test_value_alignment_middleware_json():
    app = FastAPI()
    app.add_middleware(ValueAlignmentMiddleware)

    @app.get("/api/query/test")
    async def dummy_endpoint():
        return {
            "answer": "My password: 'super_secret_password' and bearer token is Bearer 1234567890123456789",
            "final_answer": "Check client_secret = 'hidden_key'"
        }

    client = TestClient(app)
    response = client.get("/api/query/test")
    assert response.status_code == 200
    data = response.json()
    assert "super_secret_password" not in data["answer"]
    assert "Bearer 1234567890123456789" not in data["answer"]
    assert "[REDACTED]" in data["answer"]
    assert "[REDACTED]" in data["final_answer"]


def test_value_alignment_middleware_stream():
    app = FastAPI()
    app.add_middleware(ValueAlignmentMiddleware)

    @app.get("/api/query/stream_test")
    async def dummy_stream():
        async def event_generator():
            yield 'data: {"type": "token", "token": "My db_password: "}\n\n'
            yield 'data: {"type": "token", "token": "\'secret_db_pass\'"}\n\n'
            yield 'data: {"type": "done"}\n\n'
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    client = TestClient(app)
    response = client.get("/api/query/stream_test")
    assert response.status_code == 200
    
    body = response.text
    assert "secret_db_pass" not in body
    assert "[REDACTED]" in body

# ─────────────────────────────────────────────────────────
# 2. Test Active Recursive Retrieval in ResearcherAgent
# ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_researcher_agent_recursive_retrieval():
    agent = ResearcherAgent()
    
    # Mock Retriever & CRAG
    mock_retriever = AsyncMock()
    mock_crag = AsyncMock()
    
    agent._retriever = mock_retriever
    agent._crag = mock_crag

    # Mock LLM query optimizer to avoid real network requests
    agent._optimize_search_query = AsyncMock(side_effect=lambda x: x)

    # Task definition
    state = {
        "query": "Check security policies",
        "workspace_id": "ws123",
        "user_id": "u123",
        "user_role": "admin",
        "plan": {
            "tasks": [
                {"id": 1, "description": "Search in index for safety rules", "type": "retrieval"}
            ]
        },
        "current_task_index": 0,
        "raw_evidence": [],
        "approved": False
    }

    # First retrieval returns reference to 'security_policy.md'
    primary_results = [
        RetrievalResult(
            chunk_id="c1",
            content="Please see details in security_policy.md file.",
            source_url="url1",
            title="Overview Doc",
            score=0.85
        )
    ]
    
    # Mock first retriever search
    mock_retriever.search.side_effect = [
        primary_results,
        # Secondary search returns matching chunks for security_policy.md
        [
            RetrievalResult(
                chunk_id="c2",
                content="Rotate encryption keys daily.",
                source_url="url2",
                title="security_policy.md",
                score=0.90
            )
        ]
    ]

    # Mock CRAG verifications
    mock_crag.verify.side_effect = [
        VerifiedContext(
            verified_chunks=[
                VerifiedChunk(
                    chunk_id="c1",
                    content="Please see details in security_policy.md file.",
                    source_url="url1",
                    title="Overview Doc",
                    section_heading="Intro",
                    score=0.85,
                    verdict=CRAGVerdict.RELEVANT
                )
            ],
            rejected_chunks=[],
            grounding_score=1.0,
            confidence_signal="high",
            needs_web_fallback=False
        ),
        VerifiedContext(
            verified_chunks=[
                VerifiedChunk(
                    chunk_id="c2",
                    content="Rotate encryption keys daily.",
                    source_url="url2",
                    title="security_policy.md",
                    section_heading="Key Rotation",
                    score=0.90,
                    verdict=CRAGVerdict.RELEVANT
                )
            ],
            rejected_chunks=[],
            grounding_score=1.0,
            confidence_signal="high",
            needs_web_fallback=False
        )
    ]

    result = await agent.run(state)
    
    # Assert retriever was called twice (first for task, second recursively for security_policy.md)
    assert mock_retriever.search.call_count == 2
    assert mock_retriever.search.call_args_list[1][1]["question"] == "security_policy.md"
    
    # Verify both evidence blocks are aggregated
    evidence = result["raw_evidence"][0]
    assert "security_policy.md" in evidence["content"]
    assert "Rotate encryption keys daily." in evidence["content"]
    assert "Overview Doc" in evidence["content"]

# ─────────────────────────────────────────────────────────
# 3. Test Critic Backtracking in ReasoningOrchestrator
# ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critic_backtracking_and_feedback():
    orchestrator = ReasoningOrchestrator()
    
    state = {
        "query": "What is the key rotation policy?",
        "workspace_id": "ws123",
        "final_answer": "I don't know.",
        "raw_evidence": [{"content": "Evidence content"}],
        "iterations": 1,
        "plan": {
            "goal": "Core objective",
            "tasks": [{"id": 1, "description": "Find rotation policy"}]
        },
        "current_task_index": 1
    }

    # Mock evaluators at their source module
    with patch("backend.query.evaluators.evaluate_faithfulness") as mock_faith, \
         patch("backend.query.evaluators.evaluate_relevance") as mock_rel:
        
        mock_faith.return_value = {"score": 0.5, "reasoning": "Unfaithful statement detected."}
        mock_rel.return_value = {"score": 0.6, "reasoning": "Incomplete answer."}

        updates = await orchestrator.critic_node(state)
        
        # Verify backtracking triggers planning reset
        assert updates["plan"] == {}
        assert updates["current_task_index"] == 0
        assert "Critic Feedback" in updates["critic_feedback"]
        assert updates["iterations"] == 2
