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
from app.ai.prompt import get_system_instruction


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
    _SCHEDULING_TOOLS = ("discord_schedule_message", "bsky_schedule_post")
    
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
    def _claims_scheduled(message: str) -> bool:
        """Detect when the assistant text implies scheduling occurred."""
        if not message:
            return False
        patterns = [
            r"\bscheduled\b",
            r"\bi(?:'|’)?ve scheduled\b",
            r"\bi have scheduled\b",
            r"\bset up\b.*\breminder",
            r"\breminders?\b.*\bset\b",
        ]
        return any(re.search(p, message, re.IGNORECASE) for p in patterns)
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
            {"role": "system", "content": get_system_instruction()},
            {"role": "user", "content": user_text}
        ]
        
        tool_calls_log = []
        max_iterations = 10
        iteration = 0
        has_tool_calls = False
        needs_structured_response = False  # Track if we need to request structured output
        
        while iteration < max_iterations:
            iteration += 1
            
            try:
                # Prepare request parameters
                request_params = {
                    "model": "gpt-4o",  # Tool-capable model
                    "messages": messages,
                }
                
                # Cannot use both tools and structured outputs in the same request
                # Use tools on first iteration, structured output for final response
                if needs_structured_response or (has_tool_calls and iteration > 1):
                    # After tool calls or if we need structured response, use structured output
                    request_params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "dom_bot_response",
                            "strict": True,
                            "schema": self.response_schema
                        }
                    }
                else:
                    # First iteration or no tool calls yet - allow tools
                    request_params["tools"] = self.tools
                    request_params["tool_choice"] = "auto"
                
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
                
                # If we didn't request structured output (iteration 1, no tool calls),
                # make another request to get structured response
                if iteration == 1 and not has_tool_calls and "response_format" not in request_params:
                    # Re-request with structured output on next iteration
                    messages.append({
                        "role": "assistant",
                        "content": content
                    })
                    needs_structured_response = True
                    # Continue to next iteration with structured output
                    continue
                
                # Parse structured JSON response
                try:
                    response_data = json.loads(content)
                    final_response = DomBotResponse(**response_data)
                except json.JSONDecodeError as e:
                    # JSON parsing failed - log the error and provide helpful message
                    log_error("dom_bot", e, {
                        "error_type": "json_decode_error",
                        "content_preview": content[:500] if content else "None",
                        "iteration": iteration,
                        "has_tool_calls": has_tool_calls
                    })
                    # If we expected structured output but didn't get it, that's an error
                    if "response_format" in request_params:
                        final_response = DomBotResponse(
                            message="I encountered an issue processing the structured response. Please try rephrasing your request.",
                            actions=[],
                            needs_followup=False
                        )
                    else:
                        # This shouldn't happen if logic is correct, but handle gracefully
                        final_response = DomBotResponse(
                            message="I encountered an issue processing the response. Please try rephrasing your request.",
                            actions=[],
                            needs_followup=False
                        )
                except ValueError as e:
                    # Schema validation failed - log the error
                    log_error("dom_bot", e, {
                        "error_type": "schema_validation_error",
                        "content_preview": content[:500] if content else "None",
                        "iteration": iteration
                    })
                    final_response = DomBotResponse(
                        message="The response format was invalid. Please try again.",
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

                # Guardrail: don't claim something was scheduled unless a scheduling tool ran successfully.
                # This avoids the bot "sounding like it's scheduling things" while nothing was actually created.
                if self._is_schedule_intent(user_text):
                    scheduled_actions = [
                        a for a in final_response.actions
                        if a.tool_name in self._SCHEDULING_TOOLS and (a.result or {}).get("success") is True
                    ]
                    if not scheduled_actions and self._claims_scheduled(final_response.message):
                        log_event(
                            source="dom_bot",
                            event_type="schedule_claim_without_tool",
                            payload={
                                "user_text_preview": user_text[:200],
                                "assistant_message_preview": final_response.message[:200],
                                "tool_calls_count": len(final_response.actions),
                            },
                        )
                        final_response.message = (
                            "I haven’t scheduled anything yet. "
                            "Tell me exactly when (UTC) you want it scheduled (ISO 8601, ending in 'Z'), "
                            "or say it without a time and I’ll default to tomorrow at 08:00 local."
                        )
                
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
                # Log the specific error with full context
                error_type = type(e).__name__
                error_msg = str(e)
                
                # Extract more details from OpenAI errors
                error_details = {}
                error_body = None
                if hasattr(e, 'response'):
                    try:
                        if hasattr(e.response, 'json'):
                            error_details = e.response.json()
                        elif hasattr(e.response, 'text'):
                            error_body = e.response.text
                    except Exception:
                        pass
                    # Also log status code if available
                    if hasattr(e.response, 'status_code'):
                        error_details['status_code'] = e.response.status_code
                
                # Log full error context
                log_error("dom_bot", e, {
                    "error_type": error_type,
                    "iteration": iteration,
                    "user_text": user_text[:200],
                    "error_message": error_msg,
                    "error_details": error_details,
                    "error_body": error_body[:500] if error_body else None,
                    "using_structured_output": "response_format" in request_params,
                    "using_tools": "tools" in request_params
                })
                
                # Provide more specific error messages based on error type
                if "rate limit" in error_msg.lower() or "429" in error_msg:
                    user_message = "I'm being rate limited. Please wait a moment and try again."
                elif "authentication" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                    user_message = "Authentication failed. Please check API configuration."
                elif "timeout" in error_msg.lower():
                    user_message = "The request timed out. Please try again."
                elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                    user_message = "Network connection issue. Please try again."
                elif error_type == "BadRequestError":
                    # BadRequestError usually means invalid request parameters
                    if "response_format" in error_msg.lower() or "json_schema" in error_msg.lower():
                        user_message = "Request format error. This may be a configuration issue. Please check the logs."
                    elif "model" in error_msg.lower():
                        user_message = "Invalid model configuration. Please check API settings."
                    else:
                        user_message = "Invalid request parameters. Please try rephrasing your request or check the configuration."
                else:
                    user_message = f"An error occurred: {error_type}. Please try again or rephrase your request."
                
                return DomBotResponse(
                    message=user_message,
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
