import os
import yaml
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

@dataclass
class RoutingContext:
    query: str
    sensitivity: str = "low"  # low | medium | high
    cost_limit: bool = False
    latency_sensitive: bool = False

@dataclass
class RoutingDecision:
    model: str
    reason: str

class ModelRouter:
    """Policy-driven router for choosing the best LLM model."""

    def __init__(self, policy_path: Optional[str] = None, settings=None):
        self.settings = settings or get_settings()
        if policy_path is None:
            policy_path = os.path.join(os.path.dirname(__file__), "model_routing_policy.yaml")
        
        self.policy = self._load_policy(policy_path)

    def _load_policy(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load model routing policy: {e}")
            return {"rules": [], "default_model": "smart_model"}

    def route(self, context: RoutingContext) -> RoutingDecision:
        """
        Evaluate routing rules against the provided context.
        """
        rules = self.policy.get("rules", [])
        
        # Safe eval environment
        eval_env = {
            "context": context,
            "len": len,
            "true": True,
            "false": False
        }

        for rule in rules:
            condition = rule.get("condition", "false")
            try:
                if eval(condition, {"__builtins__": {}}, eval_env):
                    model_key = rule.get("model")
                    model_name = getattr(self.settings, model_key, None)
                    
                    if model_name:
                        return RoutingDecision(model=model_name, reason=rule.get("reason", "Rule match"))
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.get('name')}': {e}")

        # Fallback to default smart model
        smart_model = getattr(self.settings, "openrouter_smart_model", "local-smart")
        return RoutingDecision(model=smart_model, reason="Default fallback to smart model")

def test_harness():
    """Simulate routing decisions for verification."""
    router = ModelRouter()
    
    test_cases = [
        RoutingContext(query="Hello", sensitivity="high"),
        RoutingContext(query="What is the weather?", latency_sensitive=True),
        RoutingContext(query="Explain quantum physics in detail.", cost_limit=True),
    ]

    for ctx in test_cases:
        decision = router.route(ctx)
        print(f"Query: '{ctx.query[:20]}...' | Sensitivity: {ctx.sensitivity} | Decision: {decision.model} ({decision.reason})")

if __name__ == "__main__":
    test_harness()
