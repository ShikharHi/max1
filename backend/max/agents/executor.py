"""
max/agents/executor.py

Executor node: dispatches to the selected agent or handles directly.
OTel-instrumented — emits spans per dispatch step.

Each subagent is imported and called here. Subagents are responsible for
their own OTel instrumentation (tagging with max.run_id).
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from max.core.state import MaxState
from max.otel import get_tracer

# Import subagents
from .file_manager import run_file_manager

logger = logging.getLogger(__name__)
tracer = get_tracer("max.agents.executor")

_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


def executor_node(state: MaxState) -> dict:
    run_id = state.get("run_id", "unknown")
    selected = state.get("selected_agent", "direct")
    plan = state.get("plan", "")

    with tracer.start_as_current_span("executor.dispatch") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "executor")
        span.set_attribute("max.step", f"Dispatching to: {selected}")
        span.set_attribute("max.selected_agent", selected)

        user_message = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

        result = ""
        try:
            if selected == "file_manager":
                result = run_file_manager(
                    user_message=user_message,
                    plan=plan,
                    run_id=run_id,
                )
            else:
                # Direct handling — executor is also the synthesizer for simple tasks
                result = _handle_direct(user_message, plan, run_id)

        except Exception:
            logger.exception(f"[Executor] Error dispatching to {selected}")
            result = f"Error while executing via {selected}. Please try again."

        span.set_attribute("max.result_length", len(result))
        return {"result": result}


def _handle_direct(user_message: str, plan: str, run_id: str) -> str:
    tracer_direct = get_tracer("max.agents.direct")
    with tracer_direct.start_as_current_span("direct.handle") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "direct")
        span.set_attribute("max.step", "Handling request directly")

        response = _llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You are MAX, a powerful AI assistant. "
                        f"Plan: {plan}\n"
                        "Respond helpfully and concisely."
                    )
                ),
                HumanMessage(content=user_message),
            ]
        )
        result = response.content
        span.set_attribute("max.result_preview", result[:200])
        return result
