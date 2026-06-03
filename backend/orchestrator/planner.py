import logging
from typing import List, Dict, Any, Optional
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class Planner:
    """
    Agentic Planner that decomposes intents into structured workflows.
    Supported flows: invoice-check, FAQ reply, create-ticket.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="smart")

    async def create_plan(self, intent: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given an intent and context, outputs a workflow JSON.
        Workflow Schema: {id, steps: [{id, type, skill, inputs}], state: "pending"}
        """
        prompt = f"""
        You are a Task Decomposition Planner for a Company Brain.
        Decompose the user's intent into a structured multi-step workflow.

        Intent: {intent}
        Context: {context}

        Available Skills:
        - internal_knowledge_search: Search internal documents/wiki.
        - invoice_lookup: Retrieve invoice details by ID or customer.
        - ticket_creation: Create a support ticket in Jira/Zendesk.
        - faq_matching: Match intent against known FAQ database.
        - customer_lookup: Get customer metadata and active contracts.

        Output ONLY valid JSON following this schema:
        {{
            "id": "wf_unique_id",
            "steps": [
                {{
                    "id": 1,
                    "type": "action",
                    "skill": "skill_name",
                    "inputs": {{ "param": "value" }}
                }}
            ],
            "state": "pending"
        }}

        Examples:
        - If intent is "Check invoice INV-101", steps should be [customer_lookup, invoice_lookup].
        - If intent is "How do I reset my password?", steps should be [faq_matching].
        - If intent is "My internet is down, help!", steps should be [customer_lookup, ticket_creation].
        """
        
        try:
            res = await self.llm.chat_completion("You are a workflow planner.", prompt)
            # Basic JSON extraction
            import json
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0].strip()
            elif "```" in res:
                res = res.split("```")[1].split("```")[0].strip()
            
            plan = json.loads(res)
            plan["state"] = "pending"
            return plan
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {
                "id": "fallback_plan",
                "steps": [{"id": 1, "type": "action", "skill": "internal_knowledge_search", "inputs": {"query": intent}}],
                "state": "pending"
            }
