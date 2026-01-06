"""Strict JSON schema for final Dom Bot response."""
from typing import List, Optional
from pydantic import BaseModel, Field


class Action(BaseModel):
    """Represents an action taken or scheduled."""
    tool_name: str = Field(description="Name of the tool that was called")
    args: dict = Field(description="Arguments passed to the tool")
    result: dict = Field(description="Result from tool execution")
    task_id: Optional[str] = Field(default=None, description="Task ID if action was scheduled")


class MemoryWrite(BaseModel):
    """Represents a memory write operation."""
    key: str = Field(description="Memory key")
    value: str = Field(description="Memory value")
    metadata: Optional[dict] = Field(default=None, description="Optional metadata")


class DomBotResponse(BaseModel):
    """Final structured response from Dom Bot."""
    message: str = Field(description="Directive response to send immediately")
    actions: List[Action] = Field(default_factory=list, description="Every action taken/scheduled")
    memory_write: Optional[List[MemoryWrite]] = Field(default=None, description="DB writes (optional)")
    needs_followup: bool = Field(default=False, description="Whether a followup question is needed")
    followup_question: Optional[str] = Field(default=None, description="Followup question if needed")


def get_response_schema() -> dict:
    """Get the JSON schema for structured outputs."""
    return DomBotResponse.model_json_schema()

