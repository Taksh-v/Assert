import logging
from typing import Dict, Any, Optional
from backend.orchestrator.planner import Planner
from backend.orchestrator.dispatcher import Dispatcher
from backend.orchestrator.state_manager import StateManager
from backend.ingestion.scrubber import PIIScrubber
from backend.memory.working import WorkingMemory
from backend.models.conversation import Conversation
from backend.models.query_log import QueryLog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    Coordinates planning, execution, and state persistence for agentic workflows.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.planner = Planner()
        self.dispatcher = Dispatcher(db)
        self.state_manager = StateManager(db)
        self.scrubber = PIIScrubber()
        self.working_memory = WorkingMemory()

    async def run(
        self, 
        query: str, 
        workspace_id: str, 
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a full workflow from query to completion.
        """
        history_summary = ""
        if conversation_id:
            # 0. Load History and Summarize
            stmt = select(Conversation).options(selectinload(Conversation.messages)).where(Conversation.id == conversation_id)
            result = await self.db.execute(stmt)
            conversation = result.scalars().first()
            if conversation and conversation.messages:
                # Format messages for working memory
                history = []
                for msg in conversation.messages:
                    history.append({"role": "user", "content": msg.question})
                    if msg.answer:
                        history.append({"role": "assistant", "content": msg.answer})
                
                history_summary = await self.working_memory.summarize_history(history)

        context = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "query": query,
            "conversation_id": conversation_id,
            "history_summary": history_summary
        }

        # 1. Scrub Query & Plan
        clean_query, _ = self.scrubber.scrub(query)
        plan = await self.planner.create_plan(clean_query, context)
        
        # 2. Initialize State
        execution_id = await self.state_manager.create_execution(
            workspace_id=workspace_id,
            query=query,
            initial_state=plan
        )
        
        results = []
        # 3. Dispatch each step
        for step in plan.get("steps", []):
            try:
                # Update state to 'running step X'
                await self.state_manager.update_state(execution_id, {"current_step": step["id"]})
                
                # Execute skill
                output = await self.dispatcher.dispatch(step, context)
                results.append({"step_id": step["id"], "skill": step["skill"], "output": output})
                
                # Update state with result
                await self.state_manager.update_state(execution_id, {"results": results})
                
            except Exception as e:
                logger.error(f"Step {step['id']} failed: {e}")
                await self.state_manager.update_state(execution_id, {"error": str(e)}, status="failed")
                return {"execution_id": execution_id, "status": "failed", "error": str(e)}

        # 4. Final synthesis (Simple for MVP)
        final_answer = self._synthesize(query, results)
        
        # Scrub PII
        final_answer, _ = self.scrubber.scrub(final_answer)
        
        await self.state_manager.update_state(execution_id, {"final_answer": final_answer}, status="completed")
        
        return {
            "execution_id": execution_id,
            "status": "completed",
            "answer": final_answer,
            "plan": plan,
            "results": results
        }

    def _synthesize(self, query: str, results: list) -> str:
        """Simple synthesis of results into a final string."""
        if not results:
            return "No information found."
        
        summary = "I've completed your request. Here are the findings:\n\n"
        for r in results:
            skill = r["skill"]
            output = r["output"]
            if skill == "internal_knowledge_search":
                summary += f"- Knowledge Search: {output.get('answer', 'No answer found.')}\n"
            elif skill == "invoice_lookup":
                summary += f"- Invoice {output.get('invoice_id')}: Status is {output.get('status')} and amount is {output.get('amount')} {output.get('currency')}.\n"
            elif skill == "ticket_creation":
                summary += f"- Support Ticket: Created {output.get('ticket_id')} ({output.get('status')}).\n"
            elif skill == "customer_lookup":
                summary += f"- Customer: {output.get('name')} (Tier: {output.get('tier')})"
                if output.get("email"):
                    summary += f", Email: {output.get('email')}"
                summary += ".\n"
        
        return summary
