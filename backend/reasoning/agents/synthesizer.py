"""
Response Synthesis Engine — task2_!!!! Upgrade

Generates high-fidelity executive intelligence with real confidence
scoring (replacing hardcoded 0.95) and adaptive formatting based
on query complexity.
"""
import logging
import re
from typing import Dict, Any

from backend.generation.llm_client import LLMClient
from backend.reasoning.state import ReasoningState
from backend.observability.telemetry import trace_agent_step

logger = logging.getLogger(__name__)


class SynthesizerAgent:
    """
    Response Synthesis Engine.
    Merges all findings into the final intelligence report with
    citation anchors and computed confidence scores.
    """

    def __init__(self, model: str = "groq/llama-3.3-70b-versatile"):
        self.client = LLMClient()
        self.model = model

    @trace_agent_step("synthesizer_agent")
    async def run(self, state: ReasoningState) -> Dict[str, Any]:
        """
        Merge and analyze raw evidence and synthesize the final report.
        """
        query = state["query"]
        evidence = state.get("raw_evidence", [])
        logger.info("Synthesizing final answer for: %s", query)

        # 1. Format raw evidence blocks
        evidence_parts = []
        for e in evidence:
            task_desc = e.get("task_description", "Unknown Task")
            content = e.get("content", "")
            evidence_parts.append(
                f"--- EVIDENCE BLOCK (Task: {task_desc}) ---\n{content}"
            )
        formatted_evidence = "\n\n".join(evidence_parts) if evidence_parts else "No evidence collected."

        # 2. Build source reference from evidence blocks
        source_lines = []
        source_index = 1
        for ev in evidence:
            meta_list = ev.get("source_metadata", [])
            if meta_list:
                for meta in meta_list:
                    source_lines.append(
                        f"[{source_index}] {meta.get('title', 'Unknown')} "
                        f"({meta.get('url', '#')})"
                    )
                    source_index += 1

        source_block = "\n".join(source_lines) if source_lines else "No specific sources available."

        profile_instructions = []
        profile = state.get("user_profile")
        if profile:
            tone = profile.get("tone", "neutral")
            expertise = profile.get("expertise", "intermediate")
            
            # Expertise styling
            if expertise == "beginner":
                profile_instructions.append("The user has beginner-level expertise. Simplify terminology, explain technical acronyms, and focus on foundational explanations rather than deep code or database internals.")
            elif expertise == "advanced":
                profile_instructions.append("The user has advanced-level expertise. Provide highly detailed technical specifications, cite configuration settings and raw findings directly where available.")
                
            # Tone styling
            if tone == "frustrated":
                profile_instructions.append("The user is frustrated. Maintain an extremely supportive, patient, and highly empathetic tone. Acknowledge their issue directly, clarify next steps clearly, and provide structured, step-by-step guidance.")
            elif tone == "confused":
                profile_instructions.append("The user is confused. Focus on structured clarity, define core concepts, and avoid complex or overwhelming terminology.")
            elif tone == "curious":
                profile_instructions.append("The user is curious. Provide extra technical depth, conceptual links, and explain why things are designed or behaved in this manner.")

        profile_block = "\n".join(f"- {inst}" for inst in profile_instructions) if profile_instructions else "- Use a professional, objective tone."

        prompt = f"""You are the Chief Intelligence Officer and Senior Systems Analyst. 
Analyze the collected evidence and synthesize a high-fidelity executive intelligence report for the query: "{query}".

GOAL: Determine root causes, identify patterns, and correlate temporal events.

ADAPTIVE STYLE & TONE GUIDELINES:
{profile_block}

EVIDENCE COLLECTED:
{formatted_evidence}

AVAILABLE SOURCES:
{source_block}

Generate a comprehensive, professional report including:

## Summary
A clear 2-3 sentence executive summary.

## Key Findings
Bulleted key points with inline citations [1], [2] where applicable.

## Analysis
Detailed explanation with root cause patterns, causal relationships, and patterns found in the evidence.

## Recommendations
Actionable next steps.

RULES:
- Use inline citations [1], [2] matching the AVAILABLE SOURCES list.
- Be specific and evidence-based.
- If evidence is insufficient, note the gap honestly.
- Use clean Markdown formatting.
"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Chief Intelligence Officer. Provide "
                            "elite business intelligence with proper citations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,
            )

            report = response.choices[0].message.content

            # ── Real confidence calculation ──────────────────
            confidence = self._calculate_confidence(state, report)

            return {
                "final_answer": report,
                "confidence_score": confidence,
                "synthesized_findings": [report], # backward compatibility
            }

        except Exception as e:
            logger.error("Synthesis failed: %s", e)
            return {
                "final_answer": "Error generating final report.",
                "confidence_score": 0.0,
            }

    def _calculate_confidence(
        self, state: Dict[str, Any], report: str
    ) -> float:
        """
        Calculate real confidence score based on multiple signals.
        Replaces the previous hardcoded 0.95.
        """
        scores = []

        # Signal 1: Evidence coverage — how many tasks produced evidence?
        evidence = state.get("raw_evidence", [])
        plan = state.get("plan", {})
        total_tasks = len(plan.get("tasks", []))
        if total_tasks > 0:
            tasks_with_evidence = sum(
                1
                for e in evidence
                if e.get("content")
                and "not found" not in e.get("content", "").lower()
                and "error" not in e.get("source", "").lower()
            )
            scores.append(tasks_with_evidence / total_tasks)

        # Signal 2: Source diversity — did we get evidence from multiple sources?
        unique_sources = set()
        for e in evidence:
            for meta in e.get("source_metadata", []):
                unique_sources.add(meta.get("url", ""))
        if unique_sources:
            # More sources = higher confidence, up to 1.0
            diversity_score = min(len(unique_sources) / 3, 1.0)
            scores.append(diversity_score)

        # Signal 3: CRAG grounding — check if evidence came from verified sources
        verified_count = sum(
            1 for e in evidence if "verified" in e.get("source", "")
        )
        if evidence:
            scores.append(verified_count / len(evidence))

        # Signal 4: Citation usage — did the report actually cite sources?
        citations_found = len(re.findall(r"\[\d+\]", report))
        if citations_found > 0:
            scores.append(min(citations_found / 3, 1.0))  # 3+ citations = max
        else:
            scores.append(0.3)  # Penalty for no citations

        # Signal 5: Report length — very short reports are low confidence
        word_count = len(report.split())
        if word_count < 50:
            scores.append(0.3)
        elif word_count < 150:
            scores.append(0.6)
        else:
            scores.append(0.8)

        # Weighted average
        if scores:
            confidence = sum(scores) / len(scores)
        else:
            confidence = 0.5  # Default when no signals available

        # Clamp to [0.1, 0.95] — never 0 (we always tried) or 1.0 (never perfect)
        confidence = max(0.1, min(0.95, confidence))

        logger.info(
            "Confidence calculated: %.2f (signals: %s)",
            confidence,
            [f"{s:.2f}" for s in scores],
        )

        return round(confidence, 2)
