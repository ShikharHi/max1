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
    message: str
    run_id: str = Field(default_factory=new_id)


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
