import logging
import json
from typing import Dict, Any
from backend.generation.llm_client import LLMClient
from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)

class PlannerAgent:
    """
    Step 8: Query Planning Engine.
    Decomposes complex enterprise questions into structured reasoning tasks.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.client = LLMClient()
        self.model = model

    @trace_agent_step("planner_agent")
    async def run(self, state: ReasoningState) -> Dict[str, Any]:

        """
        Analyze the query and generate a multi-step reasoning plan.
        """
        query = state["query"]
        logger.info(f"Planning reasoning for: {query}")

        prompt = f"""
        You are the Head of Enterprise Strategy. Analyze the user query and create a deep reasoning plan.
        Break the problem into sub-tasks that require gathering evidence from Documentation, Graph Relationships, or Temporal Timelines.

        QUERY: "{query}"

        OUTPUT FORMAT (JSON):
        {{
          "goal": "Explain the core objective (e.g., Root Cause Analysis of X)",
          "tasks": [
            {{
              "id": 1,
              "description": "What specifically to research first",
              "type": "retrieval|graph|temporal",
              "dependencies": []
            }},
            {{
              "id": 2,
              "description": "Next logical step in the investigation",
              "type": "retrieval|graph|temporal",
              "dependencies": [1]
            }}
          ],
          "initial_hypotheses": ["hypothesis 1", "hypothesis 2"]
        }}
        """

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert strategic planner. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            plan_data = json.loads(content)
            
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
