import os
import yaml
import logging
import ast
import operator
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

    def _eval_node(self, node, env: dict) -> Any:
        operators = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
        }

        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # fallback
            return node.n
        elif isinstance(node, ast.Str):  # fallback
            return node.s
        elif isinstance(node, ast.NameConstant):  # fallback
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise NameError(f"Name '{node.id}' is not defined")
        elif isinstance(node, ast.Attribute):
            val = self._eval_node(node.value, env)
            return getattr(val, node.attr)
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                res = None
                for val in node.values:
                    res = self._eval_node(val, env)
                    if not res:
                        return res
                return res
            elif isinstance(node.op, ast.Or):
                res = None
                for val in node.values:
                    res = self._eval_node(val, env)
                    if res:
                        return res
                return res
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left, env)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, env)
                op_type = type(op)
                if op_type not in operators:
                    raise TypeError(f"Unsupported comparison operator: {op_type}")
                if not operators[op_type](left, right):
                    return False
            return True
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, env)
            right = self._eval_node(node.right, env)
            op_type = type(node.op)
            if op_type not in operators:
                raise TypeError(f"Unsupported binary operator: {op_type}")
            return operators[op_type](left, right)
        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func, env)
            args = [self._eval_node(arg, env) for arg in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, env) for kw in node.keywords}
            return func(*args, **kwargs)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, env)
            if isinstance(node.op, ast.Not):
                return not operand
            elif isinstance(node.op, ast.USub):
                return -operand
            raise TypeError(f"Unsupported unary operator: {type(node.op)}")
        else:
            raise TypeError(f"Unsupported AST node type: {type(node)}")

    def _evaluate_condition(self, condition_str: str, env: dict) -> bool:
        try:
            tree = ast.parse(condition_str, mode="eval")
            return bool(self._eval_node(tree.body, env))
        except Exception as e:
            logger.error(f"AST evaluation error for condition '{condition_str}': {e}")
            return False

    def route(self, context: RoutingContext) -> RoutingDecision:
        """
        Evaluate routing rules against the provided context.
        """
        rules = self.policy.get("rules", [])
        
        # Safe evaluation environment
        eval_env = {
            "context": context,
            "len": len,
            "true": True,
            "false": False
        }

        for rule in rules:
            condition = rule.get("condition", "false")
            if self._evaluate_condition(condition, eval_env):
                model_key = rule.get("model")
                model_name = getattr(self.settings, model_key, None)
                
                if model_name:
                    return RoutingDecision(model=model_name, reason=rule.get("reason", "Rule match"))

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
