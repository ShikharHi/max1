"""
max/api/models.py — Request/response schemas.
"""

from typing import Optional
from pydantic import BaseModel, Field
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


class CreateThreadRequest(BaseModel):
    metadata: dict = Field(default_factory=dict)


class ThreadResponse(BaseModel):
    thread_id: str
    created_at: str
    metadata: dict


class SendMessageRequest(BaseModel):
    message: Optional[str] = None
    run_id: str = Field(default_factory=new_id)
    checkpoint_id: Optional[str] = None
    fork_values: Optional[dict] = None


class PluginToggleRequest(BaseModel):
    enabled: bool


class PluginResponse(BaseModel):
    id: str
    name: str
    type: str
    description: str
    enabled: bool
    capabilities: list[str]
    framework: str = "any"


class MessageDict(BaseModel):
    type: str
    content: str
    name: Optional[str] = None
    id: Optional[str] = None


class CheckpointSnapshotResponse(BaseModel):
    checkpoint_id: str
    parent_checkpoint_id: Optional[str] = None
    step: int
    source: str
    created_at: str
    next_nodes: list[str]
    values: dict


class TurnResponse(BaseModel):
    """A single user-visible turn: one human message + one AI reply."""
    turn_index: int               # 1-based human-friendly index
    user_message: str             # the human input
    ai_reply: str                 # the final synthesized reply
    created_at: str               # timestamp of the human message
    # checkpoint to target for /undo or /edit (the __start__ checkpoint
    # that was created just BEFORE this turn's human message was processed)
    fork_checkpoint_id: str
    # checkpoint of the final state for this turn (useful for replay)
    result_checkpoint_id: str

