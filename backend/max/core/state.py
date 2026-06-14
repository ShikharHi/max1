"""
max/core/state.py

Shared state schema for the MAX graph.
Steps live in OTel, not in graph state — clean separation.
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MaxState(TypedDict):
    # Full message history with reducer that appends
    messages: Annotated[list[BaseMessage], add_messages]
    # Router's intent classification
    intent: Optional[str]
    # Router's selected agent/tool
    selected_agent: Optional[str]
    # Structured plan from router
    plan: Optional[str]
    # Final synthesized result
    result: Optional[str]
    # Current run_id — passed to all nodes for OTel tagging
    run_id: Optional[str]
    # HITL: whether user confirmed plan execution
    confirmed: Optional[bool]


class RunConfig(TypedDict):
    thread_id: str
    run_id: str
