from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

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
    query_id: Optional[Any] = None
    conversation_id: Optional[Any] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
