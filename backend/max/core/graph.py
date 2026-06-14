"""
max/core/graph.py

Compiles the root MAX StateGraph:
  Router → Executor → Synthesizer → END

Checkpointed with AsyncSqliteSaver.
HITL via interrupt() can be added to executor_node when needed.
"""

import os
from pathlib import Path

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from max.agents import router_node, executor_node, synthesizer_node
from max.core.state import MaxState

DB_PATH = Path(os.getenv("DATABASE_PATH", "./max.db"))


def build_graph(checkpointer: AsyncSqliteSaver) -> StateGraph:
    builder = StateGraph(MaxState)

    builder.add_node("router", router_node)
    builder.add_node("executor", executor_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.set_entry_point("router")
    builder.add_edge("router", "executor")
    builder.add_edge("executor", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile(checkpointer=checkpointer)


# Graph instance is created per-lifespan in main.py with the async checkpointer
