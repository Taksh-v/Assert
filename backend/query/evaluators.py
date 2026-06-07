import logging
import json
import re
from typing import Dict, Any, Optional
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Initialize a fast model client for cost-effective evaluation
_eval_client = None

def _get_client():
    global _eval_client
    if _eval_client is None:
        # Using the "fast" model configuration (e.g. Gemini Lite or local Ollama)
        _eval_client = LLMClient(model_type="fast")
    return _eval_client


async def evaluate_faithfulness(context: str, answer: str) -> Dict[str, Any]:
    """
    Evaluates whether the generated answer is faithful to the provided context.
    Returns a dictionary with 'score' (float 0.0-1.0) and 'reasoning' (str).
    """
    if not context or not answer:
        return {"score": 1.0, "reasoning": "Context or answer empty; evaluation skipped."}

    system_prompt = (
        "You are an expert quality evaluation bot. Your task is to judge if the generated answer is "
        "completely grounded in the provided context blocks. Do not allow any extrapolation, external knowledge, "
        "or speculation.\n\n"
        "You MUST respond ONLY with a valid JSON object of the following format, without markdown wrapping:\n"
        "{\n"
        "  \"reasoning\": \"Step-by-step reasoning explaining if facts in the answer exist in the context.\",\n"
        "  \"score\": 0.95\n"
        "}"
    )

    user_prompt = (
        f"[PROVIDED CONTEXT]:\n{context}\n\n"
        f"[GENERATED ANSWER]:\n{answer}\n\n"
        "Verify if every statement in the answer is backed by the context. Respond ONLY in the requested JSON structure."
    )

    try:
        client = _get_client()
        response_text = await client.chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0
        )
        
        # Clean response text in case LLM wrapped it in markdown code blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        data = json.loads(clean_text)
        score = float(data.get("score", 1.0))
        reasoning = str(data.get("reasoning", "Faithfulness checked."))
        return {"score": max(0.0, min(1.0, score)), "reasoning": reasoning}

    except Exception as e:
        logger.warning("TELEMETRY_WARNING: Faithfulness evaluation failed to parse: %s. Raw response: %s", e, response_text if 'response_text' in locals() else '')
        
        # Attempt regex fallback
        try:
            if 'response_text' in locals():
                score_match = re.search(r'"score"\s*:\s*(0\.\d+|1\.0|1|0)', response_text)
                if score_match:
                    return {
                        "score": float(score_match.group(1)),
                        "reasoning": "Score parsed via regex fallback."
                    }
        except Exception:
            pass
            
        return {
            "score": 0.8, 
            "reasoning": f"Evaluation system parser fallback due to error: {str(e)}"
        }


async def evaluate_relevance(question: str, answer: str) -> Dict[str, Any]:
    """
    Evaluates whether the generated answer directly addresses and is relevant to the question.
    Returns a dictionary with 'score' (float 0.0-1.0) and 'reasoning' (str).
    """
    if not question or not answer:
        return {"score": 1.0, "reasoning": "Question or answer empty; evaluation skipped."}

    system_prompt = (
        "You are an expert quality evaluation bot. Your task is to judge if the generated answer is "
        "relevant, useful, and directly answers the user's question. Ensure the answer does not contain fluff.\n\n"
        "You MUST respond ONLY with a valid JSON object of the following format, without markdown wrapping:\n"
        "{\n"
        "  \"reasoning\": \"Step-by-step reasoning explaining if the answer fully answers the user's query.\",\n"
        "  \"score\": 0.90\n"
        "}"
    )

    user_prompt = (
        f"[QUESTION]:\n{question}\n\n"
        f"[GENERATED ANSWER]:\n{answer}\n\n"
        "Verify if the answer directly solves the query. Respond ONLY in the requested JSON structure."
    )

    try:
        client = _get_client()
        response_text = await client.chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0
        )
        
        # Clean response text in case LLM wrapped it in markdown code blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        data = json.loads(clean_text)
        score = float(data.get("score", 1.0))
        reasoning = str(data.get("reasoning", "Relevance checked."))
        return {"score": max(0.0, min(1.0, score)), "reasoning": reasoning}

    except Exception as e:
        logger.warning("TELEMETRY_WARNING: Relevance evaluation failed to parse: %s. Raw response: %s", e, response_text if 'response_text' in locals() else '')
        
        # Attempt regex fallback
        try:
            if 'response_text' in locals():
                score_match = re.search(r'"score"\s*:\s*(0\.\d+|1\.0|1|0)', response_text)
                if score_match:
                    return {
                        "score": float(score_match.group(1)),
                        "reasoning": "Score parsed via regex fallback."
                    }
        except Exception:
            pass
            
        return {
            "score": 0.8, 
            "reasoning": f"Evaluation system parser fallback due to error: {str(e)}"
        }
