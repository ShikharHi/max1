"""
max/agents/router.py

Router node: classifies user intent, selects agent/tool, builds a plan.
OTel-instrumented — emits spans that flow to the frontend Steps Panel.
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from max.core.state import MaxState
from max.otel import get_tracer
from max.plugins import registry

logger = logging.getLogger(__name__)
tracer = get_tracer("max.agents.router")

_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


def router_node(state: MaxState) -> dict:
    run_id = state.get("run_id") or "unknown"

    with tracer.start_as_current_span("router.classify") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "router")
        span.set_attribute("max.step", "Classifying intent and selecting agent")

        user_message = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                content = msg.content
                user_message = content if isinstance(content, str) else str(content)
                break

        system_prompt = (
            "You are MAX's intelligent router. Your job is to classify the user's "
            "intent and route it to the best available agent or tool.\n\n"
            + registry.build_router_prompt()
        )

        try:
            response = _llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            )
            raw_content = response.content if isinstance(response.content, str) else str(response.content)
            raw = raw_content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())

            intent = parsed.get("intent", "general")
            selected = parsed.get("selected_agent", "direct")
            plan = parsed.get("plan", "Handle directly")

        except Exception:
            logger.exception("[Router] Failed to parse LLM routing response")
            intent = "general"
            selected = "direct"
            plan = "Handle the request directly"

        span.set_attribute("max.intent", intent)
        span.set_attribute("max.selected_agent", selected)
        span.set_attribute("max.plan", plan)

        logger.info(f"[Router] intent={intent} agent={selected}")
        return {
            "intent": intent,
            "selected_agent": selected,
            "plan": plan,
        }
