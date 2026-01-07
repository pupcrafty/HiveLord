"""Tool definitions for Dom Bot function calling."""
from typing import Dict, Any


def get_tools() -> list[Dict[str, Any]]:
    """Get all available tools as OpenAI function definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": "memory_search",
                "description": "Search memory/events in the database by query string",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "memory_upsert",
                "description": "Insert or update a memory entry in the database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Memory key (unique identifier)"
                        },
                        "value": {
                            "type": "string",
                            "description": "Memory value/content"
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional metadata dictionary",
                            "additionalProperties": True
                        }
                    },
                    "required": ["key", "value"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "discord_send_now",
                "description": "Send a message to Discord immediately",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message text to send"
                        }
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "discord_schedule_message",
                "description": "Schedule a Discord message to be sent at a specific UTC datetime",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message text to send"
                        },
                        "when_utc": {
                            "type": "string",
                            "description": "ISO 8601 datetime string in UTC ending with 'Z' (e.g., '2026-01-06T17:30:00Z'). MUST be a FUTURE datetime relative to the current time provided in the system message. For recurring check-ins, calculate each timestamp relative to the current time (e.g., +2 hours, +4 hours, +6 hours from now)."
                        }
                    },
                    "required": ["message", "when_utc"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "bsky_schedule_post",
                "description": "Schedule a Bluesky post (text + optional image) at a specific UTC datetime",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Post text content"
                        },
                        "when_utc": {
                            "type": "string",
                            "description": "ISO 8601 datetime string in UTC ending with 'Z' (e.g., '2026-01-06T17:30:00Z'). MUST be a FUTURE datetime relative to the current time provided in the system message. For recurring check-ins, calculate each timestamp relative to the current time (e.g., +2 hours, +4 hours, +6 hours from now)."
                        },
                        "image_url": {
                            "type": "string",
                            "description": "Optional URL to image to include in post"
                        },
                        "image_bytes": {
                            "type": "string",
                            "description": "Optional base64-encoded image bytes"
                        }
                    },
                    "required": ["text", "when_utc"]
                }
            }
        }
    ]


def get_tool_names() -> list[str]:
    """Get list of allowed tool names for validation."""
    return [tool["function"]["name"] for tool in get_tools()]


