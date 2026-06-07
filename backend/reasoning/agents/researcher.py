"""
Research Specialist Agent — task2_!!!! Activation

Replaces the stubbed researcher with a real retrieval-backed agent.
Uses the Phase 2 Retrieval Intelligence Layer (HybridRetriever + CRAG)
to gather verified evidence for the planning tasks.
"""
import logging
from typing import Dict, Any, Optional

from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """
    Multi-Agent Research Specialist.
    Uses the production retrieval pipeline to gather evidence for each
    planned task. Chunks are CRAG-verified before being added to evidence.
    """

    def __init__(self):
        self._retriever = None
        self._crag = None

    def _ensure_retriever(self):
        """Lazy-init the retriever to avoid circular imports."""
        if self._retriever is None:
            from backend.query.retriever import Retriever
            self._retriever = Retriever()
        if self._crag is None:
            from backend.query.crag_verifier import CRAGVerifier
            self._crag = CRAGVerifier()

    @trace_agent_step("researcher_agent")
    async def run(self, state: ReasoningState, task_index: int = None) -> Dict[str, Any]:
        """
        Execute the current task in the plan by retrieving multi-stream context.
        Replaces the previous stub with real retrieval + CRAG verification.
        """
        plan = state["plan"]
        tasks = plan.get("tasks", [])
        idx = task_index if task_index is not None else state["current_task_index"]

        if idx >= len(tasks):
            return {"should_continue": False}

        current_task = tasks[idx]
        desc_lower = current_task.get("description", "").lower()
        if any(k in desc_lower for k in ["approve", "confirm", "write"]) and not state.get("approved"):
            from backend.reasoning.schemas import get_approval_schema
            logger.info("Task requires approval: %s", current_task["description"])
            return {
                "awaiting_approval": True,
                "suspend_schema": get_approval_schema(current_task["description"]),
                "should_continue": False,
            }

        workspace_id = state.get("workspace_id", "")
        user_id = state.get("user_id")
        user_role = state.get("user_role", "employee")
        logger.info("Researching Task %d: %s with role %s", idx + 1, current_task["description"], user_role)

        # Initialize retriever lazily
        self._ensure_retriever()

        # Build an optimized search query from the task description
        search_query = await self._optimize_search_query(current_task["description"])
        task_type = current_task.get("type", "retrieval")

        evidence_content = ""
        evidence_source = "retrieval_intelligence_p2"
        source_metadata = []

        try:
            if task_type in ("retrieval", "temporal"):
                # Use the production hybrid retriever with RBAC roles
                results = await self._retriever.search(
                    question=search_query,
                    workspace_id=workspace_id,
                    top_k=5,
                    user_id=user_id,
                    user_role=user_role
                )


                if results:
                    # CRAG-verify the results
                    verified = await self._crag.verify(
                        question=search_query,
                        chunks=results,
                        workspace_id=workspace_id,
                    )

                    # Use only verified chunks
                    verified_chunks = verified.verified_chunks
                    if verified_chunks:
                        evidence_parts = []
                        for vc in verified_chunks:
                            heading = f" ({vc.section_heading})" if vc.section_heading else ""
                            evidence_parts.append(
                                f"Source: {vc.title}{heading}\n"
                                f"Relevance: {vc.verdict.value} (score: {vc.score:.2f})\n"
                                f"Content: {vc.content}"
                            )
                            source_metadata.append({
                                "title": vc.title,
                                "url": vc.source_url,
                                "score": vc.score,
                            })
                        evidence_content = "\n\n---\n\n".join(evidence_parts)
                        evidence_source = f"retrieval_verified (grounding: {verified.grounding_score:.2f})"
                    else:
                        evidence_content = (
                            f"No verified evidence found for: {search_query}. "
                            f"CRAG rejected all {len(results)} retrieved chunks."
                        )
                        evidence_source = "retrieval_rejected_by_crag"
                else:
                    evidence_content = f"No documents found for: {search_query}"
                    evidence_source = "retrieval_empty"

            elif task_type == "graph":
                # Graph-based retrieval
                try:
                    from backend.graph.graph_store import GraphStore
                    graph = GraphStore()
                    # Extract potential entities from the task description
                    potential_entities = [
                        w for w in search_query.split() if w[0:1].isupper()
                    ]
                    graph_data = []
                    for entity in potential_entities[:3]:
                        cluster = await graph.async_get_context(entity)
                        relationships = cluster.get("relationships", [])
                        if relationships:
                            graph_data.extend(relationships)

                    if graph_data:
                        evidence_content = (
                            "Graph relationships found:\n"
                            + "\n".join(str(r) for r in graph_data[:10])
                        )
                        evidence_source = "knowledge_graph"
                    else:
                        evidence_content = f"No graph relationships found for entities in: {search_query}"
                        evidence_source = "knowledge_graph_empty"
                except Exception as ge:
                    logger.warning("Graph retrieval failed: %s", ge)
                    evidence_content = f"Graph retrieval failed: {ge}"
                    evidence_source = "knowledge_graph_error"
            else:
                evidence_content = f"Unknown task type '{task_type}'. Retrieved context for: {search_query}"
                evidence_source = "fallback"

        except Exception as e:
            logger.error("Research retrieval failed for task %d: %s", idx + 1, e)
            evidence_content = f"Retrieval error for task: {current_task['description']}. Error: {str(e)}"
            evidence_source = "retrieval_error"

        # Build evidence block
        evidence_block = {
            "task_id": current_task["id"],
            "task_description": current_task["description"],
            "content": evidence_content,
            "source": evidence_source,
            "source_metadata": source_metadata,
        }

        return {
            "raw_evidence": [evidence_block],
            "current_task_index": idx + 1,
            "should_continue": idx + 1 < len(tasks),
        }

    async def _optimize_search_query(self, task_description: str) -> str:
        """Use a fast LLM template to transform narrative task descriptions into keyword-dense search terms."""
        from backend.core.llm_client import LLMClient
        try:
            client = LLMClient(model_type="fast")
            system_prompt = (
                "You are a search query optimizer. Extract only the primary keywords, entities, "
                "and search terms from the input task description. Keep it under 6 words and return ONLY the keywords."
            )
            res = await client.chat_completion(
                system_prompt=system_prompt,
                user_prompt=task_description,
                temperature=0.0,
                max_tokens=24
            )
            opt = res.strip()
            if opt:
                logger.info(f"Optimized search query: '{task_description}' -> '{opt}'")
                return opt
            return task_description
        except Exception as e:
            logger.warning(f"Failed to optimize search query: {e}")
            return task_description

