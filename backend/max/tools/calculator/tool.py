"""
max/tools/calculator/tool.py

Calculator tool — evaluates mathematical expressions safely.
"""

import ast
import logging
import operator

from max.otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("max.tools.calculator")

# Safe operators only
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node using only safe arithmetic operations."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _SAFE_OPS[op_type](_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _SAFE_OPS[op_type](_safe_eval(node.operand))
    else:
        raise ValueError(f"Unsupported node type: {type(node).__name__}")


def _evaluate_expression(expr: str) -> str:
    """Parse and safely evaluate a mathematical expression string."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        result = _safe_eval(tree.body)
        # Format nicely: show int if result is whole number
        if isinstance(result, float) and result.is_integer():
            return str(int(result))
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        return f"Error evaluating expression: {e}"


async def run(message: str, plan: str, run_id: str) -> str:
    """
    Entry point for the Calculator tool.
    Signature: async (message, plan, run_id) -> str
    """
    with tracer.start_as_current_span("calculator.run") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "calculator")
        span.set_attribute("max.step", "Evaluating expression")

        # Extract the mathematical expression from the message
        # Simple heuristic: look for lines that look like expressions
        expression = message.strip()
        # Remove common prefixes people use
        for prefix in ["calculate", "compute", "evaluate", "what is", "what's", "="]:
            if expression.lower().startswith(prefix):
                expression = expression[len(prefix):].strip()
                break
        expression = expression.rstrip("?").strip()

        result_value = _evaluate_expression(expression)
        result = f"**{expression} = {result_value}**"

        span.set_attribute("max.expression", expression)
        span.set_attribute("max.result", result_value)
        return result
