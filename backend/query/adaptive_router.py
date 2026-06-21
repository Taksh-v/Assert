"""
Adaptive Response Router — task2_!!!!

Routes queries to the optimal response tier based on complexity,
saving tokens and latency for simple queries while enabling deep
multi-agent reasoning when needed.

Tiers:
    DIRECT     — No retrieval. Greetings, follow-ups, chit-chat. (~200ms)
    FAST_RAG   — Retrieve → CRAG verify → single-pass generate.  (~800ms)
    FULL_SWARM — Multi-agent: Plan → Research → Analyze → Synthesize. (~3-5s)
    TOOL_EXEC  — External tool execution (GitHub, Jira, etc.).   (varies)
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from backend.reasoning.supervisor import SupervisorAgent, QueryIntent
from backend.query.resolution import ResponseTier
from backend.observability.telemetry import tracer

logger = logging.getLogger(__name__)


_ROUTE_CACHE = {}  # query.lower() -> RouteDecision


class RouteDecision(BaseModel):
    """The router's output: which tier to use and why."""
    tier: ResponseTier
    intent: QueryIntent
    rationale: str = ""
    estimated_complexity: str = "low"   # low / medium / high
    required_tools: list[str] = Field(default_factory=list)
    skip_retrieval: bool = False


class AdaptiveRouter:
    """
    Classifies queries and routes them to the optimal response tier.
    Combines fast heuristic checks with the LLM-based SupervisorAgent.
    """

    # Heuristic: queries shorter than this word count are likely simple
    SHORT_QUERY_THRESHOLD = 5
    # Keywords that strongly suggest action requests
    ACTION_KEYWORDS = {
        "create", "make", "send", "post", "deploy", "update", "delete",
        "open", "close", "assign", "file", "submit", "trigger",
    }
    FACTUAL_PREFIXES = {
        "what is", "who is", "where is", "when is", "what are", "who are",
        "where are", "when are", "how many", "how much", "what was", "who was",
    }
    # Greetings and small talk
    GREETING_PATTERNS = {
        "hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
        "bye", "goodbye", "good morning", "good afternoon", "good evening",
        "sure", "got it", "understood", "cool", "great", "awesome",
    }

    def __init__(self):
        self.supervisor = SupervisorAgent()

    async def route(
        self,
        query: str,
        reasoning_mode: bool = False,
    ) -> RouteDecision:
        """
        Classify the query and return the optimal response tier.

        If reasoning_mode is forced by the user, always route to FULL_SWARM.
        Otherwise, use fast heuristics first, then fall back to LLM classification.
        """
        cache_key = f"{query.strip().lower()}:{reasoning_mode}"
        if cache_key in _ROUTE_CACHE:
            return _ROUTE_CACHE[cache_key]

        with tracer.start_as_current_span("router.route") as span:
            span.set_attribute("query", query[:200])
            span.set_attribute("reasoning_mode", reasoning_mode)

            if reasoning_mode:
                decision = RouteDecision(
                    tier=ResponseTier.FULL_SWARM,
                    intent=QueryIntent.DEEP_ANALYSIS,
                    rationale="Reasoning mode explicitly requested by user",
                    estimated_complexity="high",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # --- Fast-path heuristics (no LLM call) ---
            lower = query.lower().strip()

            # 1. Greeting detection
            if lower in self.GREETING_PATTERNS or (
                len(lower.split()) <= 2 and "?" not in lower
            ):
                span.set_attribute("route", "direct")
                decision = RouteDecision(
                    tier=ResponseTier.DIRECT,
                    intent=QueryIntent.CONVERSATIONAL,
                    rationale="Simple greeting or acknowledgment detected",
                    estimated_complexity="low",
                    skip_retrieval=True,
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # 2. Follow-up / context-dependent detection
            follow_up_prefixes = [
                "tell me more", "explain that", "what about",
                "can you elaborate", "go deeper", "more details",
                "what do you mean", "why is that",
            ]
            if any(lower.startswith(prefix) for prefix in follow_up_prefixes):
                # Follow-ups still need retrieval but can use fast path
                span.set_attribute("route", "fast_rag_followup")
                decision = RouteDecision(
                    tier=ResponseTier.FAST_RAG,
                    intent=QueryIntent.QUICK_LOOKUP,
                    rationale="Follow-up question detected, using fast path with conversation context",
                    estimated_complexity="low",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # 3. Short factual lookup
            if any(lower.startswith(prefix) for prefix in self.FACTUAL_PREFIXES):
                span.set_attribute("route", "fast_rag_lookup")
                decision = RouteDecision(
                    tier=ResponseTier.FAST_RAG,
                    intent=QueryIntent.QUICK_LOOKUP,
                    rationale="Short factual lookup detected",
                    estimated_complexity="low",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # 4. Action keyword detection
            first_word = lower.split()[0] if lower.split() else ""
            if first_word in self.ACTION_KEYWORDS:
                span.set_attribute("route", "tool_exec")
                decision = RouteDecision(
                    tier=ResponseTier.TOOL_EXEC,
                    intent=QueryIntent.ACTION_REQUEST,
                    rationale=f"Action verb '{first_word}' detected",
                    estimated_complexity="medium",
                    required_tools=self._guess_tools(lower),
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # 5. Comparison keyword detection
            comparison_tokens = ("compare", "versus", "vs", "tradeoff", "difference between")
            if any(token in lower for token in comparison_tokens):
                span.set_attribute("route", "fast_rag_comparison")
                decision = RouteDecision(
                    tier=ResponseTier.FAST_RAG,
                    intent=QueryIntent.COMPARISON,
                    rationale="Comparison request detected",
                    estimated_complexity="medium",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # 6. Common question keywords heuristic (to bypass LLM supervisor calls)
            question_words = {"how", "why", "what", "who", "where", "when", "which", "list", "show", "describe", "explain", "find", "get"}
            query_tokens = set(lower.split())
            if query_tokens & question_words:
                span.set_attribute("route", "fast_rag_heuristic")
                decision = RouteDecision(
                    tier=ResponseTier.FAST_RAG,
                    intent=QueryIntent.QUICK_LOOKUP,
                    rationale="Heuristic: query contains question or information retrieval keywords",
                    estimated_complexity="medium",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            # --- LLM-based classification (for non-trivial queries) ---
            try:
                classification = await self.supervisor.classify_intent(query)
                intent = classification.intent
                tools = classification.required_tools

                tier = self._intent_to_tier(intent)
                span.set_attribute("route", tier.value)
                span.set_attribute("intent", intent.value)

                decision = RouteDecision(
                    tier=tier,
                    intent=intent,
                    rationale=classification.reasoning,
                    estimated_complexity=self._estimate_complexity(intent, query),
                    required_tools=tools,
                    skip_retrieval=(intent == QueryIntent.CONVERSATIONAL),
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

            except Exception as e:
                logger.warning("Router classification failed: %s. Defaulting to FAST_RAG.", e)
                span.record_exception(e)
                span.set_attribute("route", "fast_rag_fallback")
                decision = RouteDecision(
                    tier=ResponseTier.FAST_RAG,
                    intent=QueryIntent.QUICK_LOOKUP,
                    rationale=f"Classification error, defaulting to fast path: {e}",
                    estimated_complexity="medium",
                )
                _ROUTE_CACHE[cache_key] = decision
                return decision

    def _intent_to_tier(self, intent: QueryIntent) -> ResponseTier:
        """Map supervisor intent to response tier."""
        mapping = {
            QueryIntent.CONVERSATIONAL: ResponseTier.DIRECT,
            QueryIntent.QUICK_LOOKUP: ResponseTier.FAST_RAG,
            QueryIntent.COMPARISON: ResponseTier.FAST_RAG,
            QueryIntent.DEEP_ANALYSIS: ResponseTier.FULL_SWARM,
            QueryIntent.ACTION_REQUEST: ResponseTier.TOOL_EXEC,
        }
        return mapping.get(intent, ResponseTier.FAST_RAG)

    def _estimate_complexity(self, intent: QueryIntent, query: str) -> str:
        """Estimate query complexity for downstream token budget decisions."""
        if intent in (QueryIntent.CONVERSATIONAL,):
            return "low"
        lower = query.lower()
        word_count = len(query.split())
        # Multi-clause or comparison queries are always high complexity
        multi_clause_markers = (" and ", " also ", " as well as ", " in addition ", " furthermore ")
        comparison_markers = ("compare", "versus", " vs ", "difference between", "tradeoff")
        if any(m in lower for m in multi_clause_markers):
            return "high"
        if any(m in lower for m in comparison_markers):
            return "high"
        if intent in (QueryIntent.DEEP_ANALYSIS,):
            return "high"
        if intent in (QueryIntent.COMPARISON,):
            return "high"
        # Long queries typically require detailed answers
        if word_count > 15:
            return "high"
        if word_count > 8:
            return "medium"
        return "low"

    def _guess_tools(self, query: str) -> list[str]:
        """Guess which tools might be needed from the query text."""
        tools = []
        tool_keywords = {
            "github": ["github", "repo", "repository", "pr", "pull request", "issue"],
            "jira": ["jira", "ticket", "sprint", "backlog", "story"],
            "slack": ["slack", "channel", "message", "dm"],
            "notion": ["notion", "page", "wiki", "doc"],
        }
        for tool, keywords in tool_keywords.items():
            if any(kw in query for kw in keywords):
                tools.append(tool)
        return tools
