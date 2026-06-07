import logging
import json
from typing import Dict, Any, List
from sqlalchemy import select
from backend.core.database import async_session
from backend.models.query_log import QueryLog, FeedbackType
from backend.core.llm_impl import SharedLLMClient

logger = logging.getLogger(__name__)

class CognitiveGovernanceAgent:
    """
    Autonomous Cognitive Governance Agent (CGA).
    Monitors the execution telemetry and user interaction logs.
    Diagnoses failure modes and logs knowledge gap ledgers to optimize the RAG pipeline.
    """

    def __init__(self):
        self.llm_client = SharedLLMClient(model_type="smart")

    async def audit_negative_feedback_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Scans query logs for entries marked with negative feedback.
        Diagnoses whether the failure was due to routing, retrieval, verification, or synthesis error.
        """
        logger.info("Starting cognitive audit of negative feedback logs (limit=%d)...", limit)
        failures = []

        async with async_session() as session:
            # Query query logs with negative feedback
            stmt = (
                select(QueryLog)
                .where(QueryLog.feedback == FeedbackType.NEGATIVE)
                .order_by(QueryLog.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            logs = result.scalars().all()

            for log in logs:
                diagnostics = await self.diagnose_failure(
                    question=log.question,
                    answer=log.answer or "",
                    sources=log.sources or [],
                    eval_reasoning=log.eval_reasoning or ""
                )
                
                log_entry = {
                    "query_log_id": log.id,
                    "question": log.question,
                    "failure_mode": diagnostics.get("failure_mode", "UNKNOWN"),
                    "rationale": diagnostics.get("rationale", "No explanation generated"),
                    "suggested_actions": diagnostics.get("suggested_actions", [])
                }
                failures.append(log_entry)
                logger.warning(
                    "QueryLog %s audited: failure_mode=%s, suggestion=%s",
                    log.id, log_entry["failure_mode"], log_entry["rationale"][:100]
                )

        return failures

    async def diagnose_failure(self, question: str, answer: str, sources: list, eval_reasoning: str) -> Dict[str, Any]:
        """
        Utilizes LLM diagnostic capabilities to determine why a query resulted in a negative response.
        """
        system_prompt = (
            "You are a Senior RAG Systems Debugger. "
            "Analyze the failure metrics and output a JSON dictionary with the keys: "
            "'failure_mode' (string, choose from: ROUTING_ERROR, RETRIEVAL_GAP, VERIFICATION_HALLUCINATION, SYNTHESIS_LOGIC_ERROR, OTHER), "
            "'rationale' (string explanation), and "
            "'suggested_actions' (list of strings)."
        )

        user_prompt = f"""
        User Query: {question}
        Assistant Answer: {answer}
        Retrieved Sources: {json.dumps(sources)}
        Evaluation Telemetry: {eval_reasoning}
        
        Diagnose:
        """

        try:
            response = await self.llm_client.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=256
            )
            # Try to locate JSON block
            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return {"failure_mode": "OTHER", "rationale": response, "suggested_actions": []}
        except Exception as e:
            logger.error("Failed to run failure diagnosis: %s", e)
            return {"failure_mode": "DIAGNOSTIC_FAILED", "rationale": str(e), "suggested_actions": []}
