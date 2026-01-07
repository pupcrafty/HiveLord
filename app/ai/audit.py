"""Audit logging for Dom Bot tool calls and responses."""
from typing import Dict, Any, List
from datetime import datetime, timezone

from app.core.logger import log_event
from app.ai.contracts import DomBotResponse


def log_tool_call(tool_name: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Log a tool call and its result."""
    log_event(
        source="dom_bot",
        event_type="tool_call",
        payload={
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


def log_final_response(response: DomBotResponse, user_text: str, channel_id: str, user_id: str) -> None:
    """Log the final structured response from Dom Bot."""
    log_event(
        source="dom_bot",
        event_type="final_response",
        payload={
            "user_text": user_text[:200],  # Truncate for safety
            "channel_id": channel_id,
            "user_id": user_id,
            "message": response.message[:500],
            "actions_count": len(response.actions),
            "actions": [
                {
                    "tool_name": action.tool_name,
                    "task_id": action.task_id
                }
                for action in response.actions
            ],
            "needs_followup": response.needs_followup,
            "followup_question": response.followup_question,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


def log_conversation_turn(
    user_text: str,
    response: DomBotResponse,
    tool_calls: List[Dict[str, Any]],
    channel_id: str,
    user_id: str
) -> None:
    """Log a complete conversation turn with all tool calls."""
    log_event(
        source="dom_bot",
        event_type="conversation_turn",
        payload={
            "user_text": user_text[:200],
            "channel_id": channel_id,
            "user_id": user_id,
            "tool_calls_count": len(tool_calls),
            "tool_calls": tool_calls,
            "response_message": response.message[:500],
            "actions_count": len(response.actions),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


