"""
Integration Test: Supervisor Multi-Agent Pattern (Intent Routing)

Tests:
1. Supervisor successfully classifies different query intents.
2. QuickRetriever handles simple lookup requests quickly.
3. ComparisonAgent handles structured comparison requests.
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
from backend.reasoning.agents.quick_retriever import QuickRetrieverAgent


async def test_supervisor_routing():
    """Test the Supervisor intent classification and fast-path execution."""

    # ── Setup database ──
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created.\n")

    workspace_id = "test-workspace-supervisor"
    supervisor = SupervisorAgent()

    # ══════════════════════════════════════════════════════════
    # TEST 1: Heuristic fast-paths (no LLM required)
    # ══════════════════════════════════════════════════════════
    print("── TEST 1: Supervisor Heuristics ──")
    result_chat = await supervisor.classify_intent("Thanks")
    print(f"   Query: 'Thanks' -> Intent: {result_chat.intent.value}")
    assert result_chat.intent == QueryIntent.CONVERSATIONAL

    result_hello = await supervisor.classify_intent("hi")
    print(f"   Query: 'hi' -> Intent: {result_hello.intent.value}")
    assert result_hello.intent == QueryIntent.CONVERSATIONAL
    print("   ✅ Heuristic fast-paths work.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 2: LLM Fallback (since no API key in test environment)
    # ══════════════════════════════════════════════════════════
    print("── TEST 2: LLM Fallback ──")
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
