import aiohttp
import logging
from typing import Dict, Any, Optional
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class WrenAITool:
    """
    Analytical Intelligence Bridge (Layer 5/6).
    Connects the Agent Orchestrator to the WrenAI Semantic Layer.
    Enables Text-to-SQL querying over structured enterprise data.
    """

    def __init__(self, endpoint: str = "http://localhost:5566"):
        self.endpoint = endpoint

    async def ask_data(self, query: str) -> Dict[str, Any]:
        """
        Sends a natural language query to WrenAI and returns the SQL result.
        """
        logger.info(f"Analytical query to WrenAI: {query}")
        
        # WrenAI 'ask' endpoint structure
        url = f"{self.endpoint}/v1/ask"
        payload = {"query": query}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "answer": data.get("answer"),
                            "sql": data.get("sql"),
                            "results": data.get("results", []),
                            "status": "success"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"WrenAI error ({response.status}): {error_text}")
                        return {"status": "error", "message": "Analytical engine unavailable"}
        except Exception as e:
            logger.error(f"WrenAI connection failed: {e}")
            return {"status": "error", "message": "Connection to logical brain failed"}
