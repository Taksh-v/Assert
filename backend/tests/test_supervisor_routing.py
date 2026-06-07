"""
Integration Test: Supervisor Multi-Agent Pattern (Intent Routing)

Tests:
1. AdaptiveRouter handles heuristic fast-paths (greetings, actions, factuals).
2. Supervisor LLM fallback defaults to QUICK_LOOKUP when offline.
3. QuickRetriever handles simple lookup requests.
"""
import sys
import asyncio
from unittest.mock import MagicMock

# ── Mock external dependencies for offline testing ──
mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MagicMock()
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context
sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_supervisor.db"
os.environ["GROQ_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""

from backend.core.database import engine, Base
from backend.reasoning.supervisor import SupervisorAgent, QueryIntent
from backend.query.adaptive_router import AdaptiveRouter
from backend.query.resolution import ResponseTier
from backend.reasoning.agents.quick_retriever import QuickRetrieverAgent
from backend.core.llm_impl import SharedLLMClient
from unittest.mock import AsyncMock

# Monkeypatch SharedLLMClient to fail instantly during offline tests (no retries/timeouts)
SharedLLMClient.chat_completion = AsyncMock(side_effect=Exception("Mock offline error"))

class MockChat:
    class Completions:
        def create(self, *args, **kwargs):
            raise Exception("Mock offline error")
    def __init__(self):
        self.completions = self.Completions()

SharedLLMClient.chat = property(lambda self: MockChat())


async def test_supervisor_routing():
    """Test the Supervisor intent classification and fast-path execution."""

    # ── Setup database ──
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created.\n")

    workspace_id = "test-workspace-supervisor"
    router = AdaptiveRouter()
    supervisor = SupervisorAgent()

    # ══════════════════════════════════════════════════════════
    # TEST 1: Router Heuristic fast-paths (no LLM required)
    # ══════════════════════════════════════════════════════════
    print("── TEST 1: Router Heuristics ──")
    result_thanks = await router.route("Thanks")
    print(f"   Query: 'Thanks' -> Tier: {result_thanks.tier.value}, Intent: {result_thanks.intent.value}")
    assert result_thanks.tier == ResponseTier.DIRECT
    assert result_thanks.intent == QueryIntent.CONVERSATIONAL

    result_hi = await router.route("hi")
    print(f"   Query: 'hi' -> Tier: {result_hi.tier.value}, Intent: {result_hi.intent.value}")
    assert result_hi.tier == ResponseTier.DIRECT
    assert result_hi.intent == QueryIntent.CONVERSATIONAL

    result_factual = await router.route("What is our PTO policy?")
    print(f"   Query: 'What is our PTO policy?' -> Tier: {result_factual.tier.value}")
    assert result_factual.tier == ResponseTier.FAST_RAG
    assert result_factual.intent == QueryIntent.QUICK_LOOKUP

    result_compare = await router.route("Compare Slack vs Teams")
    print(f"   Query: 'Compare Slack vs Teams' -> Tier: {result_compare.tier.value}")
    assert result_compare.tier == ResponseTier.FAST_RAG
    assert result_compare.intent == QueryIntent.COMPARISON

    result_action = await router.route("Create a GitHub issue for the bug")
    print(f"   Query: 'Create a GitHub issue...' -> Tier: {result_action.tier.value}")
    assert result_action.tier == ResponseTier.TOOL_EXEC
    assert result_action.intent == QueryIntent.ACTION_REQUEST
    print("   ✅ Router heuristic fast-paths work.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 2: Supervisor LLM Fallback (no API key = error → QUICK_LOOKUP)
    # ══════════════════════════════════════════════════════════
    print("── TEST 2: Supervisor LLM Fallback ──")
    result_complex = await supervisor.classify_intent("Why did our Q3 revenue drop based on the financial reports?")
    print(f"   Query: 'Why did our Q3 revenue drop...' -> Intent: {result_complex.intent.value}")
    assert result_complex.intent == QueryIntent.QUICK_LOOKUP
    print(f"   Reasoning: {result_complex.reasoning}")
    print("   ✅ LLM Fallback works correctly (defaults to QUICK_LOOKUP).\n")

    # ══════════════════════════════════════════════════════════
    # TEST 3: QuickRetriever Agent execution (mocked LLM)
    # ══════════════════════════════════════════════════════════
    print("── TEST 3: QuickRetriever execution ──")
    quick_agent = QuickRetrieverAgent()
    quick_agent.retrieval_orchestrator.retrieve_reasoning_context = AsyncMock(
        return_value="Mocked context about PTO policy"
    )
    
    # It will fallback due to missing client and return an error message cleanly
    res = await quick_agent.execute("What is the company PTO policy?", workspace_id)
    print(f"   Result confidence: {res['confidence']}")
    print(f"   Result answer: {res['answer']}")
    
    assert "Error: LLM client unavailable" in res["answer"], "Expected graceful error from missing client"
    assert res["confidence"] == 0.0
    print("   ✅ QuickRetrieverAgent executes and fails gracefully when offline.\n")

    # ══════════════════════════════════════════════════════════
    # CLEANUP
    # ══════════════════════════════════════════════════════════
    print("🎉 All Supervisor integration tests passed!")

    # Clean up test database
    try:
        os.remove("test_supervisor.db")
    except:
        pass


if __name__ == "__main__":
    asyncio.run(test_supervisor_routing())
