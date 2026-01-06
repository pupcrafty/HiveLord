"""Dom Bot brain - OpenAI Responses API agent loop."""
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from openai import OpenAI

from app.config.settings import get_settings
from app.core.logger import log_event, log_error
from app.ai.contracts import DomBotResponse, Action, get_response_schema
from app.ai.tools import get_tools, get_tool_names
from app.ai.tool_handlers import TOOL_HANDLERS
from app.ai.audit import log_tool_call, log_final_response, log_conversation_turn
from app.ai.prompt import SYSTEM_INSTRUCTION


class DomBot:
    """Dom Bot controller using OpenAI Responses API."""

    _DISALLOWED_PHRASES = (
        "would you like",
        "do you want me to",
        "i can help",
    )
    _REWRITE_PATTERNS = (
        (re.compile(r"^\s*would you like(?: me)? to (?P<rest>.+)$", re.IGNORECASE), "Please {rest}."),
        (re.compile(r"^\s*do you want me to (?P<rest>.+)$", re.IGNORECASE), "Please {rest}."),
        (re.compile(r"^\s*i can help(?: you)?(?: with)? (?P<rest>.+)$", re.IGNORECASE), "Please {rest}."),
    )
    
    def __init__(self, discord_bot=None, bluesky_client=None):
        self.settings = get_settings()
        api_key = getattr(self.settings, 'openai_api_key', None)
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.discord_bot = discord_bot
        self.bluesky_client = bluesky_client
        self.tools = get_tools()
        self.tool_names = get_tool_names()
        self.response_schema = get_response_schema()
        
        if not self.client:
            log_event(
                source="dom_bot",
                event_type="initialization_error",
                payload={"error": "OpenAI API key not configured"}
            )
    
    def _validate_tool_name(self, tool_name: str) -> bool:
        """Validate that tool name is in allowlist."""
        return tool_name in self.tool_names

    def _rewrite_disallowed_phrasing(self, message: str) -> tuple[str, bool, str | None]:
        """Rewrite disallowed phrasing into an imperative sentence."""
        normalized = message.strip()
        if not normalized:
            return message, False, None

        lowered = normalized.lower()
        if not any(phrase in lowered for phrase in self._DISALLOWED_PHRASES):
            return message, False, None

        for pattern, template in self._REWRITE_PATTERNS:
            match = pattern.match(normalized)
            if match:
                rest = match.group("rest").strip().rstrip("?.!")
                rest = rest.rstrip(".")
                if rest:
                    rewritten = template.format(rest=rest)
                else:
                    rewritten = "Tell me what you need."
                return rewritten, True, "pattern_match"

        return "Tell me what you need.", True, "phrase_detected"
    @staticmethod
    def _has_time_reference(user_text: str) -> bool:
        """Check whether the user specified a time of day."""
        time_patterns = [
            r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
            r"\b\d{1,2}:\d{2}\b",
            r"\b(noon|midnight|morning|afternoon|evening|night|tonight)\b",
        ]
        return any(re.search(pattern, user_text, re.IGNORECASE) for pattern in time_patterns)

    @staticmethod
    def _is_schedule_intent(user_text: str) -> bool:
        """Detect scheduling intent in user text."""
        intent_patterns = [
            r"\bschedule\b",
            r"\bremind\b",
            r"\breminder\b",
            r"\bpost\b",
            r"\bsend\b",
            r"\blater\b",
        ]
        return any(re.search(pattern, user_text, re.IGNORECASE) for pattern in intent_patterns)

    @staticmethod
    def _detect_platform(user_text: str) -> Optional[str]:
        """Detect requested platform from user text."""
        if re.search(r"\b(bsky|bluesky)\b", user_text, re.IGNORECASE):
            return "bsky"
        if re.search(r"\bdiscord\b", user_text, re.IGNORECASE):
            return "discord"
        return None

    @staticmethod
    def _default_when_utc() -> str:
        """Compute next morning at 08:00 local time, converted to UTC."""
        local_now = datetime.now().astimezone()
        next_morning_local = (local_now + timedelta(days=1)).replace(
            hour=8,
            minute=0,
            second=0,
            microsecond=0
        )
        return next_morning_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    
    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        channel_id: str,
        image_data: Optional[bytes] = None,
        image_content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a tool call."""
        if not self._validate_tool_name(tool_name):
            error_msg = f"Unknown tool: {tool_name}"
            log_error("dom_bot", ValueError(error_msg), {"tool": tool_name})
            return {"error": error_msg}
        
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            error_msg = f"No handler for tool: {tool_name}"
            log_error("dom_bot", ValueError(error_msg), {"tool": tool_name})
            return {"error": error_msg}
        
        try:
            # Special handling for tools that need additional context
            if tool_name == "discord_send_now":
                result = await handler(args, self.discord_bot)
            elif tool_name == "discord_schedule_message":
                result = await handler(args, self.discord_bot, channel_id)
            elif tool_name == "bsky_schedule_post":
                result = await handler(args, self.bluesky_client, image_data, image_content_type)
            else:
                result = await handler(args)
            
            return result
        except Exception as e:
            log_error("dom_bot", e, {"tool": tool_name, "args": args})
            return {"error": str(e)}
    
    async def respond(
        self,
        user_text: str,
        channel_id: str,
        user_id: str,
        image_data: Optional[bytes] = None,
        image_content_type: Optional[str] = None
    ) -> DomBotResponse:
        """
        Process user input and return structured response.
        
        Args:
            user_text: User's message text
            channel_id: Discord channel ID
            user_id: Discord user ID
            image_data: Optional image bytes if image was attached
            image_content_type: Optional image content type
            
        Returns:
            DomBotResponse with message, actions, etc.
        """
        if not self.client:
            return DomBotResponse(
                message="Dom Bot is not configured. OpenAI API key is required.",
                actions=[],
                needs_followup=False
            )

        if self._is_schedule_intent(user_text) and not self._has_time_reference(user_text):
            platform = self._detect_platform(user_text) or "discord"
            when_utc = self._default_when_utc()
            if platform == "bsky":
                tool_name = "bsky_schedule_post"
                tool_args = {"text": user_text, "when_utc": when_utc}
                message = "Tomorrow at 08:00 local. Scheduled on Bluesky."
            else:
                tool_name = "discord_schedule_message"
                tool_args = {"message": user_text, "when_utc": when_utc}
                message = "Tomorrow at 08:00 local. Scheduled on Discord."

            tool_result = await self._execute_tool(
                tool_name,
                tool_args,
                channel_id,
                image_data,
                image_content_type
            )

            tool_calls_log = [{
                "tool_name": tool_name,
                "args": tool_args,
                "result": tool_result
            }]

            actions = [
                Action(
                    tool_name=tool_name,
                    args=tool_args,
                    result=tool_result,
                    task_id=tool_result.get("task_id")
                )
            ]

            final_response = DomBotResponse(
                message=message,
                actions=actions,
                needs_followup=False
            )

            log_conversation_turn(
                user_text,
                final_response,
                tool_calls_log,
                channel_id,
                user_id
            )

            return final_response
        
        # Build conversation context
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_text}
        ]
        
        tool_calls_log = []
        max_iterations = 10
        iteration = 0
        has_tool_calls = False
        
        while iteration < max_iterations:
            iteration += 1
            
            try:
                # Prepare request parameters
                request_params = {
                    "model": "gpt-4o",  # Tool-capable model
                    "messages": messages,
                }
                
                # Add tools on first iteration or if we haven't had tool calls yet
                if iteration == 1 or not has_tool_calls:
                    request_params["tools"] = self.tools
                    request_params["tool_choice"] = "auto"
                
                # Add structured output for final responses
                request_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "dom_bot_response",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
                
                # Call OpenAI
                response = self.client.chat.completions.create(**request_params)
                message = response.choices[0].message
                
                # Check for tool calls
                if message.tool_calls:
                    has_tool_calls = True
                    # Execute all tool calls
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}
                        
                        # Execute tool
                        tool_result = await self._execute_tool(
                            tool_name,
                            tool_args,
                            channel_id,
                            image_data,
                            image_content_type
                        )
                        
                        tool_calls_log.append({
                            "tool_name": tool_name,
                            "args": tool_args,
                            "result": tool_result
                        })
                        
                        # Add assistant message with tool call
                        messages.append({
                            "role": "assistant",
                            "content": message.content,
                            "tool_calls": [{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_call.function.arguments
                                }
                            }]
                        })
                        
                        # Add tool result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result)
                        })
                    
                    # Continue loop to get final response
                    continue
                
                # No tool calls - this should be the final response
                content = message.content
                if not content:
                    return DomBotResponse(
                        message=(
                            "Proceeding with the default assumption that you want a Discord message "
                            "sent now to the current channel. Share any changes if needed."
                        ),
                        actions=[],
                        needs_followup=False
                    )
                
                # Parse structured JSON response
                try:
                    response_data = json.loads(content)
                    final_response = DomBotResponse(**response_data)
                except (json.JSONDecodeError, ValueError) as e:
                    # Fallback: return directive response on schema failure
                    log_error("dom_bot", e, {"content": content[:200]})
                    final_response = DomBotResponse(
                        message="A systems fault interrupted execution. I corrected course. Continue.",
                        actions=[],
                        needs_followup=False
                    )

                rewritten_message, was_rewritten, reason = self._rewrite_disallowed_phrasing(
                    final_response.message
                )
                if was_rewritten:
                    log_event(
                        source="dom_bot",
                        event_type="response_rewrite",
                        payload={
                            "reason": reason,
                            "original_message": final_response.message,
                            "rewritten_message": rewritten_message,
                        },
                    )
                    final_response.message = rewritten_message
                
                # Build actions from tool calls
                actions = []
                for tool_call_log in tool_calls_log:
                    actions.append(Action(
                        tool_name=tool_call_log["tool_name"],
                        args=tool_call_log["args"],
                        result=tool_call_log["result"],
                        task_id=tool_call_log["result"].get("task_id")
                    ))
                
                final_response.actions = actions
                
                # Log conversation turn
                log_conversation_turn(
                    user_text,
                    final_response,
                    tool_calls_log,
                    channel_id,
                    user_id
                )
                
                return final_response
                
            except Exception as e:
                log_error("dom_bot", e, {
                    "iteration": iteration,
                    "user_text": user_text[:200]
                })
                return DomBotResponse(
                    message="A systems fault interrupted execution. I corrected course. Continue.",
                    actions=[],
                    needs_followup=False
                )
        
        # Max iterations reached
        return DomBotResponse(
            message=(
                "Proceeding with the default assumption that you want a Discord message "
                "sent now to the current channel. Share any changes if needed."
            ),
            actions=[],
            needs_followup=False
        )
