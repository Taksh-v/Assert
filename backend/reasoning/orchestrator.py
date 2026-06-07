import logging
from typing import Dict, Any, Callable, List

logger = logging.getLogger(__name__)


class Planner:
    """Simple planner that turns a user intent into agent tasks.

    This is intentionally minimal for an MVP; later it will produce
    structured plans with subtasks, goals, and priorities.
    """

    def plan(self, user_intent: str) -> List[Dict[str, Any]]:
        # For MVP return two tasks targeting agent_a and agent_b.
        return [
            {"agent": "agent_a", "input": user_intent},
            {"agent": "agent_b", "input": user_intent},
        ]


class Dispatcher:
    """Dispatches planned tasks to registered agent handlers."""

    def __init__(self, agents: Dict[str, Callable[[Any], Any]]):
        self.agents = agents

    def dispatch(self, task: Dict[str, Any]) -> Any:
        agent_name = task["agent"]
        if agent_name not in self.agents:
            raise KeyError(f"Unknown agent {agent_name}")
        handler = self.agents[agent_name]
        return handler(task["input"])


class Orchestrator:
    """Coordinates planning and dispatch, returns aggregated results."""

    def __init__(self, planner: Planner, dispatcher: Dispatcher):
        self.planner = planner
        self.dispatcher = dispatcher

    def orchestrate(self, user_intent: str) -> Dict[str, Any]:
        tasks = self.planner.plan(user_intent)
        results: Dict[str, Any] = {}
        for t in tasks:
            try:
                res = self.dispatcher.dispatch(t)
                results.setdefault(t["agent"], []).append(res)
            except Exception as e:
                logger.exception("Agent task failed")
                results.setdefault(t["agent"], []).append({"error": str(e)})
        return results


__all__ = ["Planner", "Dispatcher", "Orchestrator"]
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select
from backend.core.database import async_session
from backend.models.reasoning_execution import ReasoningExecution
from backend.reasoning.state import ReasoningState
from backend.reasoning.agents.planner import PlannerAgent
from backend.reasoning.agents.researcher import ResearcherAgent
from backend.reasoning.agents.synthesizer import SynthesizerAgent
from backend.evals.pipeline import ScoringPipeline
from backend.core.langfuse_wrapper import start_run, end_run, log_event
from backend.run_ledger.service import RunLedgerService

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
        builder.add_node("profiler", self.profile_node)
        builder.add_node("planner", self.planner.run)
        builder.add_node("researcher", self.researcher.run)
        builder.add_node("synthesizer", self.synthesizer.run)
        builder.add_node("critic", self.critic_node)
        
        builder.set_entry_point("profiler")
        builder.add_edge("profiler", "planner")
        builder.add_edge("planner", "researcher")
        
        def route_researcher(state: ReasoningState):
            if state.get("awaiting_approval"):
                return END
            return "researcher" if state.get("should_continue") else "synthesizer"

        builder.add_conditional_edges(
            "researcher",
            route_researcher,
            {"researcher": "researcher", "synthesizer": "synthesizer", END: END}
        )
        builder.add_edge("synthesizer", "critic")
        
        def route_critic(state: ReasoningState):
            # If both scores are high, complete
            if state.get("last_faithfulness_score", 1.0) >= 0.70 and state.get("last_relevance_score", 1.0) >= 0.70:
                return END
            # Loop cap
            if state.get("iterations", 0) >= 3:
                logger.warning("Critic iteration cap (3) reached. Ending reasoning loop.")
                return END
            # Otherwise, loop back to planning with criticism feedback
            return "planner"
            
        builder.add_conditional_edges(
            "critic",
            route_critic,
            {"planner": "planner", END: END}
        )
        
        return builder.compile()

    async def profile_node(self, state: ReasoningState) -> Dict[str, Any]:
        """Runs the CognitiveProfiler to extract intent and tone markers."""
        from backend.query.cognitive_alignment import CognitiveProfiler
        try:
            profiler = CognitiveProfiler()
            profile = await profiler.profile_query(state["query"])
            return {"user_profile": profile}
        except Exception as e:
            logger.warning(f"Failed in profile_node: {e}")
            return {"user_profile": {"tone": "neutral", "complexity": "medium", "expertise": "intermediate"}}

    async def critic_node(self, state: ReasoningState) -> Dict[str, Any]:
        """Evaluates final answer quality (faithfulness & relevance)."""
        from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance
        import asyncio
        
        answer = state.get("final_answer") or ""
        evidence_parts = []
        for e in state.get("raw_evidence", []):
            content = e.get("content", "")
            evidence_parts.append(str(content))
        context_str = "\n\n".join(evidence_parts) if evidence_parts else ""

        # Score in parallel
        faithfulness = 1.0
        relevance = 1.0
        faith_reasoning = "N/A"
        rel_reasoning = "N/A"
        
        try:
            faith_task = evaluate_faithfulness(context_str, answer)
            rel_task = evaluate_relevance(state["query"], answer)
            faith_eval, rel_eval = await asyncio.gather(faith_task, rel_task)
            
            faithfulness = faith_eval["score"]
            relevance = rel_eval["score"]
            faith_reasoning = faith_eval.get("reasoning", "")
            rel_reasoning = rel_eval.get("reasoning", "")
        except Exception as e:
            logger.warning(f"Failed to run scoring pipeline in critic_node: {e}")

        passed = faithfulness >= 0.70 and relevance >= 0.70
        feedback = f"Critic Feedback - Faithfulness: {faithfulness:.2f} ({faith_reasoning}). Relevance: {relevance:.2f} ({rel_reasoning})."
        
        logger.info(f"Critique results: faithfulness={faithfulness:.2f}, relevance={relevance:.2f}, passed={passed}")
        
        # If it failed and we are looping back, clear plan so planner can rebuild it with the feedback
        updates = {
            "last_faithfulness_score": faithfulness,
            "last_relevance_score": relevance,
            "critic_feedback": None if passed else feedback,
            "iterations": state.get("iterations", 0) + 1
        }
        if not passed:
            updates["plan"] = {}
            updates["current_task_index"] = 0
            
        return updates


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
        request_id: Optional[str] = None,
        user_input: Optional[str] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """
        Runs the reasoning swarm durably. Persists state checkpoints to PostgreSQL.
        Supports workflow suspension (e.g. awaiting human-in-the-loop approval) and resumption.
        """
        logger.info(f"Durable run requested. execution_id={execution_id}, request_id={request_id}, query='{query[:30]}...'")
        # start a langfuse run (best-effort) for this durable execution
        lf_run = None
        try:
            lf_run = start_run(request_id=request_id, metadata={"query": query, "workspace_id": workspace_id})
            log_event(lf_run, "execution_started", {"execution_id": execution_id, "request_id": request_id})
        except Exception:
            lf_run = None
        
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
                # Resolve user's role from workspace memberships
                user_role = "employee"
                if user_id and workspace_id:
                    try:
                        from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
                        stmt = select(WorkspaceMember.role).where(
                            WorkspaceMember.user_id == user_id,
                            WorkspaceMember.workspace_id == workspace_id
                        )
                        res = await session.execute(stmt)
                        db_role = res.scalar()
                        if db_role:
                            if db_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
                                user_role = "admin"
                            else:
                                user_role = "employee"
                    except Exception as re:
                        logger.warning(f"Failed to fetch user role for user {user_id}: {re}")

                # ── Create new execution ──
                state = {
                    "query": query,
                    "workspace_id": workspace_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "user_role": user_role,
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
                    "errors": [],
                    "critic_feedback": None,
                    "user_profile": None,
                    "last_faithfulness_score": 0.0,
                    "last_relevance_score": 0.0,
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
                try:
                    log_event(lf_run, "execution_suspended", {"execution_id": execution_id, "request_id": request_id})
                except Exception:
                    pass
                try:
                    end_run(lf_run, status="suspended")
                except Exception:
                    pass
                return self._format_result(final_state, execution_id, "suspended")
            
            # Continue to Analysis & Evaluation checks using final_state
            state = final_state
            await self._update_execution(execution_id, state, "running")
        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            state["errors"].append(str(e))
            await self._update_execution(execution_id, state, "failed")
            try:
                log_event(lf_run, "execution_failed", {"execution_id": execution_id, "request_id": request_id, "error": str(e)})
            except Exception:
                pass
            try:
                end_run(lf_run, status="error")
            except Exception:
                pass
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
        try:
            log_event(lf_run, "execution_completed", {"execution_id": execution_id, "request_id": request_id, "status": "completed"})
        except Exception:
            pass
        try:
            end_run(lf_run, status="ok")
        except Exception:
            pass
        return self._format_result(state, execution_id, "completed")

    async def _update_execution(self, execution_id: str, state: Dict[str, Any], status: str):
        async with async_session() as session:
            # Load the run record, set transient fields (state snapshot, index),
            # then delegate canonical state transition to RunLedgerService.finish_run
            result = await session.execute(select(ReasoningExecution).where(ReasoningExecution.id == execution_id))
            run = result.scalars().first()
            if not run:
                raise ValueError(f"Reasoning execution {execution_id} not found")

            # Persist the orchestration state payload and task index on the run
            run.state_snapshot = state
            run.current_task_index = state.get("current_task_index", getattr(run, "current_task_index", 0))
            run.updated_at = datetime.utcnow()

            # Use the RunLedgerService facade to perform the canonical lifecycle transition
            await RunLedgerService.finish_run(session, ReasoningExecution, execution_id, status)
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
            "flagged_for_review": state.get("flagged_for_review", False),
            "user_profile": state.get("user_profile"),
        }
