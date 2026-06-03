import logging
from typing import Dict, Any, Optional
from backend.query.query_service import QueryService

logger = logging.getLogger(__name__)

class Dispatcher:
    """
    Routes tasks to skill adapters (HTTP or local functions).
    """

    def __init__(self, db_session):
        self.db = db_session
        self.query_service = QueryService(db_session)

    async def dispatch(self, step: Dict[str, Any], context: Dict[str, Any]) -> Any:
        skill = step.get("skill")
        inputs = step.get("inputs", {})
        
        logger.info(f"Dispatching skill: {skill} with inputs: {inputs}")

        if skill == "internal_knowledge_search" or skill == "faq_matching":
            return await self._handle_knowledge_search(inputs, context)
        elif skill == "invoice_lookup":
            return await self._handle_invoice_lookup(inputs)
        elif skill == "ticket_creation":
            return await self._handle_ticket_creation(inputs, context)
        elif skill == "customer_lookup":
            return await self._handle_customer_lookup(inputs)
        else:
            raise ValueError(f"Unknown skill: {skill}")

    async def _handle_knowledge_search(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        query = inputs.get("query")
        workspace_id = context.get("workspace_id")
        user_id = context.get("user_id")
        
        result = await self.query_service.execute_query(
            question=query,
            workspace_id=workspace_id,
            user_id=user_id
        )
        # QueryResult supports __getitem__ so we can use result["answer"]
        return {"answer": result["answer"], "sources": result["sources"]}

    async def _handle_invoice_lookup(self, inputs: Dict[str, Any]) -> Any:
        # Mock implementation for MVP
        invoice_id = inputs.get("invoice_id", "INV-UNKNOWN")
        return {
            "invoice_id": invoice_id,
            "status": "paid",
            "amount": 1500.00,
            "currency": "USD",
            "due_date": "2026-06-15"
        }

    async def _handle_ticket_creation(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        # Mock implementation for MVP
        summary = inputs.get("summary", "Support Request")
        return {
            "ticket_id": "TKT-42",
            "status": "created",
            "provider": "jira",
            "summary": summary
        }

    async def _handle_customer_lookup(self, inputs: Dict[str, Any]) -> Any:
        # Mock implementation for MVP
        name = inputs.get("customer_name", "Unknown")
        return {
            "customer_id": "CUST-001",
            "name": name,
            "tier": "enterprise",
            "active_contracts": ["CON-2026-A"]
        }
