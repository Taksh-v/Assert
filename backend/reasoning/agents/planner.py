import logging
import json
import re
from typing import Dict, Any
from backend.generation.llm_client import LLMClient
from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)

class PlannerAgent:
    """
    Query Planning Engine.
    Decomposes complex enterprise questions into structured reasoning tasks.

    Uses async chat_completion() for non-blocking execution and robust
    JSON parsing to handle free-tier model responses.
    """

    def __init__(self, model: str = "groq/llama-3.3-70b-versatile"):
        self.client = LLMClient()
        self.model = model

    @trace_agent_step("planner_agent")
    async def run(self, state: ReasoningState) -> Dict[str, Any]:

        """
        Analyze the query and generate a multi-step reasoning plan.
        """
        if state.get("plan") and not state.get("critic_feedback"):
            logger.info("Plan already exists in state. Skipping planning.")
            return {}
        query = state["query"]
        logger.info(f"Planning reasoning for: {query}")

        system_prompt = "You are an expert strategic planner. Output ONLY valid JSON."

        feedback_prompt = ""
        if state.get("critic_feedback"):
            feedback_prompt = f"\n\nCRITIQUE FEEDBACK FROM PREVIOUS ATTEMPT:\n{state['critic_feedback']}\nPlease adjust your plan and task descriptions to address the feedback."

        profile_instructions = ""
        profile = state.get("user_profile")
        if profile:
            expertise = profile.get("expertise", "intermediate")
            if expertise == "beginner":
                profile_instructions = "\nADAPTATION GUIDELINE: The user has beginner-level expertise. Focus the plan on high-level conceptual verification and explaining foundational modules rather than deep configuration settings."
            elif expertise == "advanced":
                profile_instructions = "\nADAPTATION GUIDELINE: The user has advanced-level expertise. Focus the plan on detailed diagnostics, raw code/database structures, and system configurations."

        user_prompt = f"""Analyze the user query and create a reasoning plan.{feedback_prompt}{profile_instructions}
Break the problem into sub-tasks for gathering evidence.

QUERY: "{query}"

OUTPUT FORMAT (JSON):
{{
  "goal": "Core objective of the investigation",
  "tasks": [
    {{
      "id": 1,
      "description": "What to research first",
      "type": "retrieval|graph|temporal",
      "dependencies": []
    }},
    {{
      "id": 2,
      "description": "Next step",
      "type": "retrieval|graph|temporal",
      "dependencies": [1]
    }}
  ],
  "initial_hypotheses": ["hypothesis 1", "hypothesis 2"]
}}"""

        try:
            content = await self.client.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=256,
            )

            if not content:
                raise ValueError("Empty response from LLM")

            # Robust JSON parsing with regex fallback
            try:
                plan_data = json.loads(content)
            except json.JSONDecodeError:
                # Try extracting JSON from markdown code blocks
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    plan_data = json.loads(match.group(0))
                else:
                    raise ValueError("No JSON block found in planner LLM response")

            return {
                "plan": plan_data,
                "current_task_index": 0,
                "hypotheses": plan_data.get("initial_hypotheses", []),
                "iterations": state.get("iterations", 0) + 1
            }
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {
                "errors": [f"Planning error: {str(e)}"],
                "should_continue": False
            }
