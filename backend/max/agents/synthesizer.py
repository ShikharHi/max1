"""
max/agents/synthesizer.py

Synthesizer node: takes the executor's raw result and shapes it into a
well-formatted final response. Adds the response as an AIMessage.
OTel-instrumented.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from max.core.state import MaxState
from max.otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("max.agents.synthesizer")

_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)


def synthesizer_node(state: MaxState) -> dict:
    run_id = state.get("run_id") or "unknown"
    result = state.get("result") or ""
    intent = state.get("intent") or "general"

    with tracer.start_as_current_span("synthesizer.format") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "synthesizer")
        span.set_attribute("max.step", "Synthesizing final response")
        span.set_attribute("max.intent", intent)

        # If result is already well-formed, skip extra LLM call for speed
        if len(result) < 2000 and not result.strip().startswith("{"):
            final = result
        else:
            try:
                user_message = ""
                for msg in reversed(state["messages"]):
                    if isinstance(msg, HumanMessage):
                        content = msg.content
                        user_message = content if isinstance(content, str) else str(content)
                        break

                response = _llm.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are MAX. Synthesize the following execution result "
                                "into a clear, helpful response for the user. "
                                "Preserve important details. Be concise and well-formatted."
                            )
                        ),
                        HumanMessage(
                            content=(
                                f"User asked: {user_message}\n\n"
                                f"Execution result:\n{result}"
                            )
                        ),
                    ]
                )
                final = response.content if isinstance(response.content, str) else str(response.content)
            except Exception:
                logger.exception("[Synthesizer] LLM synthesis failed, returning raw result")
                final = result

        span.set_attribute("max.final_length", len(final or ""))

        return {
            "messages": [AIMessage(content=final)],
            "result": final,
        }
