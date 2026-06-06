import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.retrieval.security import apply_security_filter
from backend.query.truth_resolver import TruthResolver
from backend.query.cognitive_alignment import CognitiveProfiler, ValueAlignmentFilter
from backend.reasoning.state import ReasoningState

def test_apply_security_filter_role_exclusions():
    """Verify that employee/guest roles get chunks with sensitive keywords filtered out."""
    results = [
        {"chunk_id": "c1", "text": "normal company process", "metadata": {"title": "Onboarding", "source_url": "wiki/onboarding", "is_public": True}},
        {"chunk_id": "c2", "text": "here is the db admin password secret", "metadata": {"title": "Credentials", "source_url": "wiki/credentials", "is_public": True}},
        {"chunk_id": "c3", "text": "employee salaries overview list", "metadata": {"title": "Finance report", "source_url": "wiki/financial", "is_public": True}},
    ]

    # For 'employee', sensitive chunks should be excluded
    filtered_emp = apply_security_filter(results, user_id="u1", is_development=False, user_role="employee")
    ids_emp = [item["chunk_id"] for item in filtered_emp]
    assert "c1" in ids_emp
    assert "c2" not in ids_emp
    assert "c3" not in ids_emp

    # For 'admin', all chunks should be allowed
    filtered_admin = apply_security_filter(results, user_id="u1", is_development=False, user_role="admin")
    ids_admin = [item["chunk_id"] for item in filtered_admin]
    assert "c1" in ids_admin
    assert "c2" in ids_admin
    assert "c3" in ids_admin



def test_truth_resolver_weight_scaling():
    """Verify that TruthResolver scales scores according to source trust weight and filters < 0.4."""
    results = [
        {"chunk_id": "wiki", "text": "wiki page", "score": 0.8, "metadata": {"source_url": "notion.so/wiki", "title": "Notion Wiki"}},
        {"chunk_id": "slack", "text": "slack chat", "score": 0.9, "metadata": {"source_url": "slack.com/archive", "title": "Slack Message"}},
        {"chunk_id": "jira", "text": "jira ticket", "score": 0.6, "metadata": {"source_url": "jira.atlassian.com/ticket", "title": "Jira Ticket"}},
        {"chunk_id": "low_trust_slack", "text": "slack msg 2", "score": 0.7, "metadata": {"source_url": "slack.com/channel", "title": "Slack Msg 2"}},
    ]

    # Weights: Wiki (1.0) -> score remains 0.8 (>= 0.4, passes)
    # Slack (0.5) -> score becomes 0.9 * 0.5 = 0.45 (>= 0.4, passes)
    # Jira (0.8) -> score becomes 0.6 * 0.8 = 0.48 (>= 0.4, passes)
    # Low trust Slack (0.5) -> score becomes 0.7 * 0.5 = 0.35 (< 0.4, filtered out)
    
    resolved = TruthResolver.resolve_weights(results)
    ids = [item["chunk_id"] for item in resolved]

    assert "wiki" in ids
    assert "slack" in ids
    assert "jira" in ids
    assert "low_trust_slack" not in ids

    # Check scores were adjusted
    wiki_item = next(item for item in resolved if item["chunk_id"] == "wiki")
    slack_item = next(item for item in resolved if item["chunk_id"] == "slack")
    jira_item = next(item for item in resolved if item["chunk_id"] == "jira")

    assert pytest.approx(wiki_item["score"]) == 0.8
    assert pytest.approx(slack_item["score"]) == 0.45
    assert pytest.approx(jira_item["score"]) == 0.48


def test_value_alignment_credential_redaction():
    """Verify that ValueAlignmentFilter correctly redacts raw credentials."""
    value_filter = ValueAlignmentFilter()
    raw_content = "To access the database, use password='super_secret_password_123' and api_key=\"key_abc123\""
    
    redacted = value_filter.inspect_security(raw_content)
    assert "[REDACTED]" in redacted
    assert "super_secret_password_123" not in redacted
    assert "key_abc123" not in redacted


@pytest.mark.asyncio
@patch("backend.core.llm_client.LLMClient.chat_completion")
async def test_cognitive_profiler_parsing(mock_llm):
    """Verify that CognitiveProfiler correctly parses LLM response into structured profiles."""
    mock_llm.return_value = '{"tone": "frustrated", "complexity": "high", "expertise": "beginner"}'
    
    profiler = CognitiveProfiler()
    profile = await profiler.profile_query("why is the server down again? I don't know terminal commands.")
    
    assert profile["tone"] == "frustrated"
    assert profile["complexity"] == "high"
    assert profile["expertise"] == "beginner"


@pytest.mark.asyncio
async def test_critic_evaluation_logic():
    """Test that the critic node properly computes faithfulness and relevance and returns updates."""
    from backend.reasoning.orchestrator import ReasoningOrchestrator

    orchestrator = ReasoningOrchestrator()
    
    state: ReasoningState = {
        "query": "What is our deployment strategy?",
        "workspace_id": "ws1",
        "user_id": "u1",
        "user_role": "employee",
        "plan": {"tasks": [{"id": 1, "description": "Check deploy script", "type": "retrieval"}]},
        "current_task_index": 1,
        "raw_evidence": [{"task_id": 1, "content": "Deployments run on Kubernetes.", "source": "verified"}],
        "synthesized_findings": ["Use Kubernetes"],
        "hypotheses": [],
        "final_answer": "Deployments run on Kubernetes.",
        "confidence_score": 0.8,
        "iterations": 0,
        "max_iterations": 3,
        "should_continue": False,
        "awaiting_approval": False,
        "approved": False,
        "errors": [],
        "critic_feedback": None,
        "user_profile": None,
        "last_faithfulness_score": 0.0,
        "last_relevance_score": 0.0,
    }

    # 1. Simulate a passing critique (both evaluations score >= 0.70)
    with patch("backend.query.evaluators.evaluate_faithfulness", new_callable=AsyncMock) as mock_faith:
        mock_faith.return_value = {"score": 0.9, "reasoning": "factually correct"}
        with patch("backend.query.evaluators.evaluate_relevance", new_callable=AsyncMock) as mock_rel:
            mock_rel.return_value = {"score": 0.85, "reasoning": "fully relevant"}
            updates = await orchestrator.critic_node(state)
            
            assert updates["last_faithfulness_score"] == 0.9
            assert updates["last_relevance_score"] == 0.85
            assert updates["critic_feedback"] is None
            # Plan should NOT be cleared if passed
            assert "plan" not in updates

    # 2. Simulate a failing critique (scores < 0.70)
    with patch("backend.query.evaluators.evaluate_faithfulness", new_callable=AsyncMock) as mock_faith:
        mock_faith.return_value = {"score": 0.4, "reasoning": "hallucinated details"}
        with patch("backend.query.evaluators.evaluate_relevance", new_callable=AsyncMock) as mock_rel:
            mock_rel.return_value = {"score": 0.3, "reasoning": "off topic"}
            updates = await orchestrator.critic_node(state)
            
            assert updates["last_faithfulness_score"] == 0.4
            assert updates["last_relevance_score"] == 0.3
            assert updates["critic_feedback"] is not None
            # Plan and task index should be reset to force re-planning/re-routing
            assert updates["plan"] == {}
            assert updates["current_task_index"] == 0


@pytest.mark.asyncio
async def test_oauth_state_nonce_single_use():
    """Verify that verify_oauth_state blocks duplicate nonces and allows single-use."""
    from backend.core.database import init_db
    from backend.core.security import create_oauth_state, verify_oauth_state
    
    await init_db()
    
    workspace_id = "test-ws-id"
    # Generate the state JWT token (this creates a unique state containing a random nonce)
    state = create_oauth_state(workspace_id)
    
    # First use: should pass and return the workspace_id
    verified_ws = await verify_oauth_state(state)
    assert verified_ws == workspace_id

    # Second use (replay attack): should raise ValueError indicating state token reuse detected
    with pytest.raises(ValueError) as excinfo:
        await verify_oauth_state(state)
    assert "reuse detected" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_current_user_production_unauthorized():
    """Verify that get_current_user raises a 401 HTTPException in production when token is missing or invalid."""
    from fastapi import HTTPException
    from backend.api.users import get_current_user
    
    # Mock settings.is_development to False (Production environment)
    with patch("backend.api.users.settings") as mock_settings:
        mock_settings.is_development = False
        mock_settings.app_secret_key = "test-secret"
        
        # Test case 1: Token is completely missing
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(token=None, db=AsyncMock())
        assert excinfo.value.status_code == 401
        assert "Invalid or missing authentication token" in excinfo.value.detail
        
        # Test case 2: Token is invalid
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(token="invalid-token", db=AsyncMock())
        assert excinfo.value.status_code == 401
        assert "Invalid or missing authentication token" in excinfo.value.detail

