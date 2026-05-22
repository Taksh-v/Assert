import logging
from typing import Dict, Any
from backend.generation.llm_client import LLMClient
from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)

class SynthesizerAgent:
    """
    Step 15: Response Synthesis Engine.
    Generates high-fidelity executive intelligence and recommendations.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.client = LLMClient()
        self.model = model

    @trace_agent_step("synthesizer_agent")
    async def run(self, state: ReasoningState) -> Dict[str, Any]:

        """
        Merge all findings into the final intelligence report.
        """
        query = state["query"]
        findings = state["synthesized_findings"]
        logger.info(f"Synthesizing final answer for: {query}")

        prompt = f"""
        You are the Chief Intelligence Officer. Synthesize the final answer for the query: "{query}".
        
        ANALYTICAL FINDINGS:
        {" ".join(findings)}

        Generate a comprehensive, professional report including:
        1. EXECUTIVE SUMMARY
        2. ROOT CAUSE ANALYSIS / CORE ANSWER
        3. SUPPORTING EVIDENCE
        4. ACTIONABLE RECOMMENDATIONS
        5. CONFIDENCE SCORE (0-100%)

        Use clean Markdown formatting.
        """

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a Chief Intelligence Officer. Provide elite business intelligence."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.1
            )
            
            report = response.choices[0].message.content
            
            return {
                "final_answer": report,
                "confidence_score": 0.95 # In prod, calculate this from analysis
            }
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return {"final_answer": "Error generating final report."}
