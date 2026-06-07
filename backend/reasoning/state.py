from typing import List, Dict, Any, Optional, Annotated, TypedDict
import operator

class ReasoningState(TypedDict):
    """
    State management for the Reasoning Infrastructure Layer (Phase 3).
    Tracks the lifecycle of a complex reasoning task.
    """
    # Inputs
    query: str
    workspace_id: str
    user_id: Optional[str]
    
    # Planning (Step 8)
    plan: Dict[str, Any] # Goal, Tasks, Dependencies
    current_task_index: int
    
    # Evidence Gathering (Phase 2 Integration)
    raw_evidence: Annotated[List[Dict[str, Any]], operator.add]
    
    # Analysis (Step 11)
    synthesized_findings: Annotated[List[str], operator.add]
    hypotheses: List[str]
    
    # Output (Step 15)
    final_answer: Optional[str]
    confidence_score: float
    
    # Flow Control
    iterations: int
    max_iterations: int
    should_continue: bool
    awaiting_approval: bool
    approved: bool
    errors: List[str]
    
    # Active Critique & Profiling (Sophia Integration)
    critic_feedback: Optional[str]
    user_profile: Optional[Dict[str, Any]]
    user_role: str
    last_faithfulness_score: float
    last_relevance_score: float



