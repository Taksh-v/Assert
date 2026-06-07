"""
Integration Test: Observational Memory + Output Quality Scoring (Evals)

Tests:
1. Observer compresses raw messages into observations
2. Reflector decays and prunes old observations
3. MemoryManager assembles a two-block context window
4. All four quality scorers produce valid results
5. ScoringPipeline aggregates and persists scores
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
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_memory_evals.db")
os.environ.setdefault("GROQ_API_KEY", "")

from backend.core.database import engine, Base, async_session
from backend.models import Observation, EvalScore
from backend.memory.observer import ObserverAgent, count_tokens
from backend.memory.reflector import ReflectorAgent
from backend.memory.manager import MemoryManager
from backend.evals.base_scorer import ScorerResult
from backend.evals.completeness import CompletenessScorer
from backend.evals.pipeline import ScoringPipeline


async def test_observational_memory_and_evals():
    """Test the full memory and evaluation pipeline."""

    # ── Setup database ──
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created.\n")

    workspace_id = "test-workspace-memory"
    user_id = "test-user-1"

    # ══════════════════════════════════════════════════════════
    # TEST 1: Token counting
    # ══════════════════════════════════════════════════════════
    print("── TEST 1: Token Counting ──")
    test_text = "This is a test sentence to verify token counting works correctly."
    tokens = count_tokens(test_text)
    print(f"   Text: '{test_text}'")
    print(f"   Token count: {tokens}")
    assert tokens > 5, f"Expected > 5 tokens, got {tokens}"
    print("   ✅ Token counting works.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 2: Observer — rule-based compression
    # ══════════════════════════════════════════════════════════
    print("── TEST 2: Observer Rule-Based Compression ──")
    observer = ObserverAgent(token_threshold=50)  # Low threshold for testing

    raw_messages = [
        {"role": "user", "content": "What is our deployment strategy for the new microservices architecture?"},
        {"role": "assistant", "content": "Based on the documentation, we use a blue-green deployment strategy with canary releases."},
        {"role": "user", "content": "How does the CI/CD pipeline handle rollbacks?"},
        {"role": "assistant", "content": "The pipeline uses ArgoCD with automatic rollback triggers based on health check failures."},
        {"role": "user", "content": "Can you explain the monitoring setup for production?"},
        {"role": "assistant", "content": "We use Prometheus for metrics, Grafana for dashboards, and PagerDuty for alerting."},
    ]

    should_compress = observer.should_compress(raw_messages)
    print(f"   Messages count: {len(raw_messages)}")
    print(f"   Should compress (threshold={observer.token_threshold}): {should_compress}")
    assert should_compress, "Expected messages to exceed token threshold"

    # Run compression (will use rule-based fallback since no Groq API key)
    observations = await observer.compress(raw_messages, workspace_id, user_id)
    print(f"   Observations created: {len(observations)}")
    for obs in observations:
        print(f"     - {obs['content'][:80]}... (priority: {obs['priority']})")
    assert len(observations) >= 1, "Expected at least 1 observation"
    print("   ✅ Observer compression works.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 3: MemoryManager — store direct observations
    # ══════════════════════════════════════════════════════════
    print("── TEST 3: MemoryManager Direct Observation Storage ──")
    manager = MemoryManager()

    # Store some observations directly
    obs1_id = await manager.store_observation(
        workspace_id=workspace_id,
        content="User prefers technical depth in answers",
        category="preference",
        user_id=user_id,
        priority=0.8
    )
    obs2_id = await manager.store_observation(
        workspace_id=workspace_id,
        content="Team uses Kubernetes for container orchestration",
        category="fact",
        user_id=user_id,
        priority=0.6
    )
    obs3_id = await manager.store_observation(
        workspace_id=workspace_id,
        content="Security review required before any production deployment",
        category="decision",
        user_id=user_id,
        priority=0.9
    )

    count = await manager.get_observation_count(workspace_id, user_id)
    print(f"   Stored 3 direct observations + {len(observations)} from Observer")
    print(f"   Total active observations: {count}")
    assert count >= 3, f"Expected at least 3 observations, got {count}"
    print("   ✅ Direct observation storage works.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 4: MemoryManager — context window assembly
    # ══════════════════════════════════════════════════════════
    print("── TEST 4: Context Window Assembly ──")
    recent_messages = [
        {"role": "user", "content": "What's the latest on our API rate limiting?"},
        {"role": "assistant", "content": "We currently use a token bucket algorithm with 100 req/min per user."},
    ]

    context_window = await manager.get_context_window(
        workspace_id=workspace_id,
        working_messages=recent_messages,
        user_id=user_id
    )

    print(f"   Context window length: {len(context_window)} chars")
    print(f"   Context window tokens: {count_tokens(context_window)}")
    assert "AGENT MEMORY" in context_window, "Expected observation log block"
    assert "RECENT CONVERSATION" in context_window, "Expected working memory block"
    print(f"   ✅ Two-block context window assembled correctly.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 5: Reflector — decay and prune
    # ══════════════════════════════════════════════════════════
    print("── TEST 5: Reflector Decay & Prune ──")
    reflector = ReflectorAgent()

    # Store a low-priority old observation to test archival
    from datetime import datetime, timedelta
    async with async_session() as session:
        old_obs = Observation(
            workspace_id=workspace_id,
            user_id=user_id,
            content="[2026-01-01] Old stale observation that should be decayed",
            priority=0.05,  # Below MIN_PRIORITY threshold
            category="general",
            is_active=True,
            created_at=datetime.utcnow() - timedelta(days=30)
        )
        session.add(old_obs)
        await session.commit()

    summary = await reflector.reflect(workspace_id, user_id)
    print(f"   Reflection summary: {summary}")
    assert summary["archived"] >= 1, f"Expected at least 1 archived, got {summary['archived']}"
    print("   ✅ Reflector decay and prune works.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 6: Completeness Scorer (rule-based, no LLM needed)
    # ══════════════════════════════════════════════════════════
    print("── TEST 6: Completeness Scorer ──")
    scorer = CompletenessScorer()

    # Good answer - covers all query keywords
    result_good = await scorer.score(
        query="What is the deployment strategy and rollback mechanism?",
        output="Our deployment strategy uses blue-green deployment. The rollback mechanism is automated via health checks."
    )
    print(f"   Good answer score: {result_good.score} (passed: {result_good.passed})")
    print(f"   Reasoning: {result_good.reasoning}")
    assert result_good.score >= 0.5, f"Expected score >= 0.5 for good answer, got {result_good.score}"

    # Bad answer - misses key terms
    result_bad = await scorer.score(
        query="What is the deployment strategy and rollback mechanism?",
        output="The weather today is sunny with a high of 75 degrees."
    )
    print(f"   Bad answer score: {result_bad.score} (passed: {result_bad.passed})")
    print(f"   Reasoning: {result_bad.reasoning}")
    assert result_bad.score < 0.5, f"Expected score < 0.5 for bad answer, got {result_bad.score}"
    print("   ✅ Completeness scorer works correctly.\n")

    # ══════════════════════════════════════════════════════════
    # TEST 7: Scoring Pipeline (all scorers, fallback mode)
    # ══════════════════════════════════════════════════════════
    print("── TEST 7: Full Scoring Pipeline ──")
    pipeline = ScoringPipeline()

    # Create a mock reasoning execution for score persistence
    from backend.models.reasoning_execution import ReasoningExecution
    async with async_session() as session:
        execution = ReasoningExecution(
            workspace_id=workspace_id,
            query="What is our security policy?",
            status="completed",
            current_task_index=1,
            state_snapshot={}
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        exec_id = execution.id

    eval_result = await pipeline.evaluate(
        execution_id=exec_id,
        workspace_id=workspace_id,
        query="What is our security policy for API access?",
        output="Our security policy requires JWT authentication for all API endpoints. Rate limiting is enforced at 100 requests per minute.",
        context="API Security Policy: All endpoints require JWT bearer tokens. Rate limits are set to 100 req/min per authenticated user. OAuth2 is supported for third-party integrations."
    )

    print(f"   Aggregate score: {eval_result['aggregate_score']}")
    print(f"   All passed: {eval_result['all_passed']}")
    print(f"   Flagged for review: {eval_result['flagged_for_review']}")
    for score in eval_result['scores']:
        print(f"     - {score['scorer_name']}: {score['score']} ({'✅' if score['passed'] else '❌'})")
        print(f"       {score['reasoning'][:80]}")

    assert 0.0 <= eval_result['aggregate_score'] <= 1.0, "Aggregate score out of range"
    assert len(eval_result['scores']) == 4, f"Expected 4 scorer results, got {len(eval_result['scores'])}"

    # Verify scores were persisted
    persisted_scores = await pipeline.get_scores(exec_id)
    print(f"\n   Persisted scores in DB: {len(persisted_scores)}")
    assert len(persisted_scores) == 4, f"Expected 4 persisted scores, got {len(persisted_scores)}"
    print("   ✅ Scoring pipeline works correctly.\n")

    # ══════════════════════════════════════════════════════════
    # CLEANUP
    # ══════════════════════════════════════════════════════════
    print("🎉 All Observational Memory + Evals tests passed!")

    # Clean up test database
    try:
        os.remove("test_memory_evals.db")
    except:
        pass


if __name__ == "__main__":
    asyncio.run(test_observational_memory_and_evals())
