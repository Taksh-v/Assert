import logging
import json
from typing import Dict, Any
from backend.generation.llm_client import LLMClient
from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)

class AnalystAgent:
    """
    Step 11: Analytical Reasoning Engine.
    Correlates evidence, tests hypotheses, and identifies causal links.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.client = LLMClient()
        self.model = model

    @trace_agent_step("analyst_agent")
    async def run(self, state: ReasoningState) -> Dict[str, Any]:

        """
        Analyze the gathered evidence and synthesize findings.
        """
        evidence = state["raw_evidence"]
        query = state["query"]
        logger.info(f"Analyzing evidence for: {query}")

        if not evidence:
            return {"should_continue": False}

        # 1. Format evidence for the analyst
        formatted_evidence = "\n\n".join([
            f"--- EVIDENCE BLOCK (Task: {e['task_description']}) ---\n{e['content']}"
            for e in evidence
        ])

        prompt = f"""
        You are a Senior Systems Analyst. Analyze the following evidence collected for the query: "{query}".
        
        GOAL: Determine root causes, identify patterns, and correlate temporal events.

        EVIDENCE:
        {formatted_evidence}

        HYPOTHESES TO TEST:
        {state['hypotheses']}

        Analyze the evidence and identify:
        1. Confirmed facts.
        2. Causal relationships.
        3. Contradictions.
        4. Gaps that require more research.

        Output your analysis in a structured synthesis.
        """

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a specialized enterprise analyst. Be precise and objective."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0
            )
            
            synthesis = response.choices[0].message.content
            
            return {
                "synthesized_findings": [synthesis],
                "should_continue": False # For now, one pass analysis. Reflection can change this.
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"errors": [f"Analysis error: {str(e)}"]}
