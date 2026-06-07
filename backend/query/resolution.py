"""
Resolution Types — Structured models for the Assest response system.

Defines the canonical data models used across the query pipeline:
- QueryResolutionPlan: routing decision
- CitedSource: individual grounded citation
- VerifiedContext: CRAG-verified retrieval output
- QueryResult: final response envelope
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum


class ResponseTier(str, Enum):
    """Which response path was used."""
    DIRECT = "direct"           # No retrieval (conversational/greeting)
    FAST_RAG = "fast_rag"       # Single-pass retrieve → verify → generate
    FULL_SWARM = "full_swarm"   # Multi-agent reasoning orchestrator
    TOOL_EXEC = "tool_exec"     # External tool execution


class CRAGVerdict(str, Enum):
    """Corrective-RAG chunk relevance verdict."""
    RELEVANT = "relevant"
    AMBIGUOUS = "ambiguous"
    IRRELEVANT = "irrelevant"


class CitedSource(BaseModel):
    """A single grounded source citation."""
    id: int                                  # [1], [2], etc.
    title: str
    url: str
    section_heading: Optional[str] = None    # e.g., "Onboarding Process"
    confidence: float = 0.0                  # retrieval similarity score
    verified: bool = True                    # CRAG verification passed
    chunk_id: Optional[str] = None           # for internal tracing

    def display_label(self) -> str:
        """User-friendly label: 'Title — Section' or just 'Title'."""
        if self.section_heading:
            return f"{self.title} — {self.section_heading}"
        return self.title


class VerifiedChunk(BaseModel):
    """A retrieval chunk that has passed CRAG verification."""
    chunk_id: str
    content: str
    source_url: str
    title: str
    section_heading: Optional[str] = None
    score: float = 0.0
    verdict: CRAGVerdict = CRAGVerdict.RELEVANT
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerifiedContext(BaseModel):
    """Output of the CRAG verification layer."""
    verified_chunks: List[VerifiedChunk] = Field(default_factory=list)
    rejected_chunks: List[VerifiedChunk] = Field(default_factory=list)
    grounding_score: float = 0.0     # aggregate confidence
    confidence_signal: str = "high"  # high / medium / low / none
    needs_web_fallback: bool = False


class QueryResolutionPlan(BaseModel):
    query: Any
    intent: Any
    reasoning: Optional[Any] = None
    required_tools: List[Any] = Field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class RetrievalContext(BaseModel):
    text: Any
    sources: List[Any] = Field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ReasoningResult(BaseModel):
    answer: Any
    confidence: Any
    execution_id: Optional[Any] = None
    status: Optional[Any] = None
    iterations: Optional[Any] = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class QueryResult(BaseModel):
    answer: Any
    sources: List[Any] = Field(default_factory=list)
    citations: List[CitedSource] = Field(default_factory=list)
    citations_used: List[int] = Field(default_factory=list)
    query_id: Optional[Any] = None
    conversation_id: Optional[Any] = None
    response_tier: str = ResponseTier.FAST_RAG.value
    grounding_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
