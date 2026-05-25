import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select, update
from backend.core.database import async_session
from backend.models.reasoning_execution import ReasoningExecution
from backend.reasoning.state import ReasoningState
from backend.reasoning.agents.planner import PlannerAgent
from backend.reasoning.agents.researcher import ResearcherAgent
from backend.reasoning.agents.analyst import AnalystAgent
from backend.reasoning.agents.synthesizer import SynthesizerAgent
from backend.evals.pipeline import ScoringPipeline

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

logger = logging.getLogger(__name__)

class ReasoningOrchestrator:
    """
    Phase 3: Reasoning Infrastructure Layer Orchestrator.
    Coordinates the multi-agent swarm. Integrates durable workflow 
    execution via database-backed state checkpointing and suspend/resume actions.
    """

    def __init__(self):
        self.planner = PlannerAgent()
        self.researcher = ResearcherAgent()
        self.analyst = AnalystAgent()
        self.synthesizer = SynthesizerAgent()
        self.scoring_pipeline = ScoringPipeline()
        from backend.memory.platform import get_platform_memory
        self.memory_manager = get_platform_memory()
        
        if HAS_LANGGRAPH:
            self.workflow = self._build_workflow()
        else:
            logger.warning("LangGraph not found. Falling back to Native Orchestration.")

    def _build_workflow(self) -> Any:
        builder = StateGraph(ReasoningState)
        builder.add_node("planner", self.planner.run)
        builder.add_node("researcher", self.researcher.run)
        builder.add_node("analyst", self.analyst.run)
        builder.add_node("synthesizer", self.synthesizer.run)
        builder.set_entry_point("planner")
        builder.add_edge("planner", "researcher")
        builder.add_conditional_edges(
            "researcher",
            lambda x: "analyst" if not x["should_continue"] else "researcher",
            {"researcher": "researcher", "analyst": "analyst"}
        )
        builder.add_edge("analyst", "synthesizer")
        builder.add_edge("synthesizer", END)
        return builder.compile()

    async def run(
        self, 
        query: str, 
        workspace_id: str, 
        user_id: Optional[str] = None,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """
        Run the reasoning swarm synchronously (backwards-compatible wrapper).
        """
        result = await self.run_durable(
            query=query,
            workspace_id=workspace_id,
            user_id=user_id,
            max_iterations=max_iterations
        )
        return {
            "answer": result["answer"],
            "confidence": result["confidence"],
            "plan": result["plan"],
            "iterations": result["iterations"]
        }

    async def run_durable(
        self,
        query: str,
        workspace_id: str,
        execution_id: Optional[str] = None,
        user_input: Optional[str] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """
        Runs the reasoning swarm durably. Persists state checkpoints to PostgreSQL.
        Supports workflow suspension (e.g. awaiting human-in-the-loop approval) and resumption.
        """
        logger.info(f"Durable run requested. execution_id={execution_id}, query='{query[:30]}...'")
        
        async with async_session() as session:
            if execution_id:
                # ── Resume existing execution ──
                stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
                res = await session.execute(stmt)
                execution = res.scalars().first()
                if not execution:
                    raise ValueError(f"Reasoning execution {execution_id} not found")
                
                state = execution.state_snapshot
                
                # Resume input integration
                if user_input:
                    state["approved"] = True
                    # Log the human feedback/approval response
                    state["raw_evidence"].append({
                        "task_id": -1,
                        "task_description": "Human input/approval received",
                        "content": f"User approval/input: {user_input}",
                        "source": "human_in_the_loop"
                    })
                state["awaiting_approval"] = False
                execution.status = "running"
                await session.commit()
            else:
                # ── Create new execution ──
                state = {
                    "query": query,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "plan": {},
                    "current_task_index": 0,
                    "raw_evidence": [],
                    "synthesized_findings": [],
                    "hypotheses": [],
                    "final_answer": None,
                    "confidence_score": 0.0,
                    "iterations": 0,
                    "max_iterations": max_iterations,
                    "should_continue": True,
                    "awaiting_approval": False,
                    "approved": False,
                    "errors": []
                }
                execution = ReasoningExecution(
                    workspace_id=workspace_id,
                    query=query,
                    status="running",
                    current_task_index=0,
                    state_snapshot=state
                )
                session.add(execution)
                await session.commit()
                await session.refresh(execution)
                execution_id = execution.id

        if not HAS_LANGGRAPH:
            logger.error("LangGraph is required for reasoning orchestrator but is not installed.")
            raise RuntimeError("LangGraph missing")

        logger.info("Executing Reasoning Swarm via LangGraph StateGraph")
        try:
            # Ensure the completed_task_ids list is initialized
            if "completed_task_ids" not in state:
                state["completed_task_ids"] = []

            # Execute the LangGraph workflow
            final_state = await self.workflow.ainvoke(state)
            
            # Check if it was suspended (via AwaitApproval node or error)
            if final_state.get("awaiting_approval"):
                await self._update_execution(execution_id, final_state, "suspended")
                return self._format_result(final_state, execution_id, "suspended")
            
            # Continue to Analysis & Evaluation checks using final_state
            state = final_state
            await self._update_execution(execution_id, state, "running")
        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            state["errors"].append(str(e))
            await self._update_execution(execution_id, state, "failed")
            return self._format_result(state, execution_id, "failed")

        # ── Step 5: Quality Evaluation (Mastra-inspired Evals) ──
        eval_result = None
        if state.get("final_answer"):
            try:
                context_text = "\n".join(
                    e.get("content", "") if isinstance(e.get("content"), str) else str(e.get("content", ""))
                    for e in state.get("raw_evidence", [])
                )
                eval_result = await self.scoring_pipeline.evaluate(
                    execution_id=execution_id,
                    workspace_id=state["workspace_id"],
                    query=state["query"],
                    output=state["final_answer"],
                    context=context_text
                )
                # Use eval aggregate as the official confidence score
                state["confidence_score"] = eval_result.get("aggregate_score", state.get("confidence_score", 0.0))
                state["eval_scores"] = eval_result.get("scores", [])
                state["flagged_for_review"] = eval_result.get("flagged_for_review", False)
                logger.info(f"Eval scores: aggregate={eval_result['aggregate_score']}, flagged={eval_result['flagged_for_review']}")
            except Exception as e:
                logger.warning(f"Scoring pipeline failed (non-blocking): {e}")

        # ── Step 6: Store Memory Observation (Mastra-inspired) ──
        try:
            if state.get("final_answer"):
                confidence = state.get('confidence_score', 0.0)
                observation = (
                    f"Query: {state['query'][:100]}. "
                    f"Answer confidence: {confidence:.2f}. "
                    f"Tasks completed: {len(state.get('completed_task_ids', []))}."
                )
                await self.memory_manager.store_observation(
                    workspace_id=state["workspace_id"],
                    content=observation,
                    category="decision" if confidence > 0.7 else "fact",
                    user_id=state.get("user_id"),
                    priority=min(confidence, 0.9)
                )
        except Exception as e:
            logger.warning(f"Memory observation store failed (non-blocking): {e}")

        await self._update_execution(execution_id, state, "completed")
        return self._format_result(state, execution_id, "completed")

    async def _update_execution(self, execution_id: str, state: Dict[str, Any], status: str):
        async with async_session() as session:
            stmt = update(ReasoningExecution).where(ReasoningExecution.id == execution_id).values(
                status=status,
                current_task_index=state["current_task_index"],
                state_snapshot=state,
                updated_at=datetime.utcnow()
            )
            await session.execute(stmt)
            await session.commit()

    def _format_result(self, state: Dict[str, Any], execution_id: str, status: str) -> Dict[str, Any]:
        return {
            "execution_id": execution_id,
            "status": status,
            "answer": state.get("final_answer"),
            "confidence": state.get("confidence_score", 0.0),
            "plan": state.get("plan"),
            "iterations": state.get("iterations", 0),
            "awaiting_approval": state.get("awaiting_approval", False),
            "suspend_schema": state.get("suspend_schema"),
            "eval_scores": state.get("eval_scores", []),
            "flagged_for_review": state.get("flagged_for_review", False)
        }
