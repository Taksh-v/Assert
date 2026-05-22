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
from backend.memory.manager import MemoryManager

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
        self.memory_manager = MemoryManager()
        
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

        # Use LangGraph if available, fallback to Native Orchestration
        import os
        use_native = os.getenv("USE_NATIVE_ORCHESTRATION", "false").lower() == "true"
        
        if HAS_LANGGRAPH and not use_native:
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
        else:
            logger.warning("Executing via Native Orchestration Fallback")
            # ── Step 1: Planning ──
            if not state.get("plan"):
                plan_update = await self.planner.run(state)
                state.update(plan_update)
                if state.get("errors"):
                    await self._update_execution(execution_id, state, "failed")
                    return self._format_result(state, execution_id, "failed")
                await self._update_execution(execution_id, state, "running")

            tasks = state["plan"].get("tasks", [])

            # Ensure completed_task_ids list is in the state snapshot
            if "completed_task_ids" not in state:
                state["completed_task_ids"] = []
                if state.get("current_task_index", 0) > 0:
                    # Add all tasks up to current_task_index as completed
                    state["completed_task_ids"] = [t["id"] for t in tasks[:state["current_task_index"]]]

            # ── Step 2: Research loop with DAG orchestration & suspend checks ──
            while len(state["completed_task_ids"]) < len(tasks) and state.get("should_continue", True):
                # 1. Identify tasks ready to run (dependencies satisfied)
                completed_set = set(state["completed_task_ids"])
                ready_tasks = []
                for task in tasks:
                    if task["id"] not in completed_set:
                        deps = task.get("dependencies", [])
                        if all(dep_id in completed_set for dep_id in deps):
                            ready_tasks.append(task)

                if not ready_tasks:
                    logger.error("DAG Deadlock or cycle detected in reasoning plan!")
                    state["errors"].append("DAG Deadlock or cycle detected in reasoning plan")
                    break

                # 2. Check if any ready tasks trigger manual gating and are not yet approved
                needs_approval = False
                for task in ready_tasks:
                    desc = task.get("description", "").lower()
                    if any(k in desc for k in ["approve", "confirm", "write"]) and not state.get("approved"):
                        needs_approval = True
                        break

                if needs_approval:
                    from backend.reasoning.schemas import get_approval_schema
                    state["awaiting_approval"] = True
                    state["current_task_index"] = len(state["completed_task_ids"])
                    # Generate a suspend schema based on the first task needing approval
                    task_descriptions = [t.get("description", "") for t in ready_tasks if any(k in t.get("description", "").lower() for k in ["approve", "confirm", "write"])]
                    desc = task_descriptions[0] if task_descriptions else "Action requires approval"
                    state["suspend_schema"] = get_approval_schema(desc)
                    
                    await self._update_execution(execution_id, state, "suspended")
                    return self._format_result(state, execution_id, "suspended")

                # 3. Execute all ready tasks in parallel
                import asyncio
                
                async def run_single_task(task_obj):
                    task_idx = tasks.index(task_obj)
                    return await self.researcher.run(state, task_index=task_idx), task_obj["id"]

                logger.info(f"Executing {len(ready_tasks)} tasks in parallel: {[t['description'] for t in ready_tasks]}")
                results = await asyncio.gather(*(run_single_task(t) for t in ready_tasks))

                # 4. Process results and update state
                for research_update, task_id in results:
                    if "raw_evidence" in research_update:
                        state["raw_evidence"].extend(research_update["raw_evidence"])
                    state["completed_task_ids"].append(task_id)

                state["iterations"] = state.get("iterations", 0) + 1
                state["current_task_index"] = len(state["completed_task_ids"])
                await self._update_execution(execution_id, state, "running")
                
                if state["iterations"] >= state["max_iterations"]:
                    break

            # ── Step 3: Analysis ──
            if not state.get("synthesized_findings") and not state.get("final_answer"):
                analysis_update = await self.analyst.run(state)
                state.update(analysis_update)
                await self._update_execution(execution_id, state, "running")

            # ── Step 4: Synthesis ──
            if not state.get("final_answer"):
                synthesis_update = await self.synthesizer.run(state)
                state.update(synthesis_update)
                await self._update_execution(execution_id, state, "running")

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
