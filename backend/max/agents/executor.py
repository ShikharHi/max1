"""
max/agents/executor.py

Executor node: dispatches to the selected plugin via the registry.
OTel-instrumented — emits spans per dispatch step.

Plugins are registered by PluginRegistry (skills, tools, agents, mcp).

Execution modes
---------------
1. Python-runner plugin   — runner found in registry → call it directly
2. LLM-guided skill       — no runner, but has a SKILL.md body →
                            load body as system context, call LLM
3. Direct fallback        — no plugin matched → handle with base LLM

Runner signature:
    async (user_message: str, plan: str, run_id: str) -> str
"""

import asyncio
import logging
import concurrent.futures

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from max.core.state import MaxState
from max.otel import get_tracer
from max.plugins import registry

logger = logging.getLogger(__name__)
tracer = get_tracer("max.agents.executor")

_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


def executor_node(state: MaxState) -> dict:
    run_id   = state.get("run_id")       or "unknown"
    selected = state.get("selected_agent") or "direct"
    plan     = state.get("plan")         or ""

    with tracer.start_as_current_span("executor.dispatch") as span:
        span.set_attribute("max.run_id",        run_id)
        span.set_attribute("max.agent",         "executor")
        span.set_attribute("max.step",          f"Dispatching to: {selected}")
        span.set_attribute("max.selected_agent", selected)

        # Extract the most recent human message
        user_message = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                content = msg.content
                user_message = content if isinstance(content, str) else str(content)
                break

        result = ""
        try:
            runner = registry.get_runner(selected)

            if runner:
                # --- Mode 1: Python-runner plugin ----------------------------
                # Spin up a fresh thread (no running event loop) to use asyncio.run()
                # safely inside FastAPI's already-running loop.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, runner(user_message, plan, run_id))
                    result = future.result()

            else:
                # Check if this is an LLM-guided skill (has SKILL.md, no Python runner)
                skill_manifest = registry.get_skill_manifest(selected)

                if skill_manifest is not None and skill_manifest.is_llm_guided:
                    # --- Mode 2: LLM-guided skill ----------------------------
                    result = _handle_llm_guided_skill(
                        selected, user_message, plan, run_id
                    )
                else:
                    # --- Mode 3: Direct fallback -----------------------------
                    if selected != "direct":
                        logger.warning(
                            "[Executor] No runner found for '%s', falling back to direct",
                            selected,
                        )
                    result = _handle_direct(user_message, plan, run_id)

        except Exception:
            logger.exception("[Executor] Error dispatching to %s", selected)
            result = f"Error while executing via {selected}. Please try again."

        span.set_attribute("max.result_length", len(result))
        return {"result": result}


def _handle_llm_guided_skill(
    skill_id: str, user_message: str, plan: str, run_id: str
) -> str:
    """
    Mode 2: Execute an LLM-guided skill.

    Loads the SKILL.md body as the system context and sends the user message
    to the LLM.  The skill's instruction body acts as the runtime "plugin"
    injected into context (Claude's Level-2 loading).
    """
    skill_tracer = get_tracer(f"max.skills.{skill_id}")
    with skill_tracer.start_as_current_span(f"{skill_id}.llm_guided") as span:
        span.set_attribute("max.run_id",  run_id)
        span.set_attribute("max.agent",   skill_id)
        span.set_attribute("max.step",    "Executing LLM-guided skill")

        # Level-2 load: fetch the SKILL.md instruction body
        skill_body = registry.get_skill_body(skill_id) or ""

        system_content = (
            "You are MAX, a powerful AI assistant.\n\n"
            "## Skill Instructions\n\n"
            f"{skill_body}\n\n"
            f"## Task Plan\n{plan}\n\n"
            "Follow the skill instructions above to handle the user's request. "
            "Be concise and helpful."
        )

        response = _llm.invoke(
            [
                SystemMessage(content=system_content),
                HumanMessage(content=user_message),
            ]
        )
        result = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        span.set_attribute("max.result_preview", result[:200])
        return result


def _handle_direct(user_message: str, plan: str, run_id: str) -> str:
    """Mode 3: Handle a request directly without any plugin."""
    tracer_direct = get_tracer("max.agents.direct")
    with tracer_direct.start_as_current_span("direct.handle") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent",  "direct")
        span.set_attribute("max.step",   "Handling request directly")

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
        result = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        span.set_attribute("max.result_preview", result[:200])
        return result
