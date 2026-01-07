"""Tool handlers that execute tool calls via existing integrations."""
import asyncio
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json

from app.core.scheduler import get_scheduler
from app.core.logger import log_event, log_error
from app.storage.db import get_db_sync
from app.storage.models import Event, Memory
from app.ai.audit import log_tool_call


async def memory_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search memory/events in the database by query string.
    
    Args:
        args: Dictionary with 'query' (str) and optional 'limit' (int)
        
    Returns:
        Dictionary with 'results' list
    """
    query = args.get("query", "")
    limit = args.get("limit", 10)
    
    db = get_db_sync()
    try:
        # Search in Event table (payload_json contains searchable text)
        events = db.query(Event).filter(
            Event.payload_json.contains(query)
        ).order_by(Event.ts.desc()).limit(limit).all()
        
        results = []
        for event in events:
            try:
                payload = json.loads(event.payload_json)
            except:
                payload = {"raw": event.payload_json[:200]}
            
            results.append({
                "id": event.id,
                "source": event.source,
                "type": event.type,
                "timestamp": event.ts.isoformat(),
                "payload": payload
            })
        
        result = {"results": results, "count": len(results)}
        log_tool_call("memory_search", args, result)
        return result
    except Exception as e:
        log_error("dom_bot", e, {"tool": "memory_search", "args": args})
        return {"error": str(e), "results": []}
    finally:
        db.close()


async def memory_upsert(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert or update a memory entry in the database.
    
    Args:
        args: Dictionary with 'key' (str), 'value' (str), and optional 'metadata' (dict)
        
    Returns:
        Dictionary with 'key', 'created' (bool), 'updated' (bool)
    """
    key = args.get("key")
    value = args.get("value")
    metadata = args.get("metadata")
    
    if not key or not value:
        return {"error": "key and value are required"}
    
    db = get_db_sync()
    try:
        # Check if exists
        existing = db.query(Memory).filter(Memory.key == key).first()
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        if existing:
            existing.value = value
            existing.metadata_json = metadata_json
            existing.updated_at = datetime.now(timezone.utc)
            created = False
        else:
            memory = Memory(
                key=key,
                value=value,
                metadata_json=metadata_json
            )
            db.add(memory)
            created = True
        
        db.commit()
        
        result = {"key": key, "created": created, "updated": not created}
        log_tool_call("memory_upsert", args, result)
        return result
    except Exception as e:
        db.rollback()
        log_error("dom_bot", e, {"tool": "memory_upsert", "args": args})
        return {"error": str(e)}
    finally:
        db.close()


async def discord_send_now(args: Dict[str, Any], discord_bot) -> Dict[str, Any]:
    """
    Send a message to Discord immediately.
    
    Args:
        args: Dictionary with 'message' (str)
        discord_bot: DiscordBot instance
        
    Returns:
        Dictionary with 'success' (bool), 'message_id' (optional)
    """
    message = args.get("message", "")
    
    if not message:
        return {"error": "message is required"}
    
    try:
        await discord_bot.send_message(message)
        result = {"success": True, "message": "sent"}
        log_tool_call("discord_send_now", args, result)
        return result
    except Exception as e:
        log_error("dom_bot", e, {"tool": "discord_send_now", "args": args})
        return {"error": str(e), "success": False}


async def discord_schedule_message(
    args: Dict[str, Any],
    discord_bot,
    channel_id: str
) -> Dict[str, Any]:
    """
    Schedule a Discord message to be sent at a specific UTC datetime.
    
    Args:
        args: Dictionary with 'message' (str) and 'when_utc' (ISO 8601 string)
        discord_bot: DiscordBot instance
        channel_id: Discord channel ID
        
    Returns:
        Dictionary with 'task_id' (str), 'scheduled_for' (ISO string)
    """
    message = args.get("message", "")
    when_utc_str = args.get("when_utc", "")
    
    if not message or not when_utc_str:
        return {"error": "message and when_utc are required"}
    
    try:
        # Parse datetime - handle both Z and +00:00 formats
        when_utc_str_clean = when_utc_str.replace("Z", "+00:00")
        when_dt = datetime.fromisoformat(when_utc_str_clean)
        
        # Ensure timezone-aware (default to UTC if not specified)
        if when_dt.tzinfo is None:
            # Assume UTC if no timezone specified
            when_dt = when_dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC if different timezone
            when_dt = when_dt.astimezone(timezone.utc)
        
        # Validate future time
        now = datetime.now(timezone.utc)
        if when_dt <= now:
            # Provide helpful error message with current time
            error_msg = (
                f"Cannot schedule message in the past. "
                f"Requested: {when_dt.isoformat()}, "
                f"Current UTC: {now.isoformat()}. "
                f"Please use a FUTURE datetime relative to the current time."
            )
            log_event(
                source="dom_bot",
                event_type="scheduling_error_past_date",
                payload={
                    "requested": when_dt.isoformat(),
                    "current": now.isoformat(),
                    "message_preview": message[:100]
                }
            )
            return {"error": error_msg}
        
        # Create coroutine to send message
        async def send_scheduled_message():
            try:
                await discord_bot.send_message(message)
                log_event(
                    source="dom_bot",
                    event_type="scheduled_discord_sent",
                    payload={
                        "channel_id": channel_id,
                        "message": message[:100],
                        "scheduled_for": when_dt.isoformat()
                    }
                )
            except Exception as e:
                log_error("dom_bot", e, {
                    "tool": "discord_schedule_message",
                    "action": "send_scheduled"
                })
        
        # Schedule it
        scheduler = get_scheduler()
        task_id = scheduler.schedule_at(
            when_dt,
            send_scheduled_message(),
            name=f"discord_msg_{channel_id}",
            handler_type="discord_schedule_message",
            parameters={
                "message": message,
                "channel_id": channel_id
            }
        )
        
        result = {
            "task_id": task_id,
            "scheduled_for": when_dt.isoformat(),
            "success": True
        }
        log_tool_call("discord_schedule_message", args, result)
        return result
    except ValueError as e:
        return {"error": f"Invalid datetime format: {str(e)}"}
    except Exception as e:
        log_error("dom_bot", e, {"tool": "discord_schedule_message", "args": args})
        return {"error": str(e)}


async def bsky_schedule_post(
    args: Dict[str, Any],
    bluesky_client,
    image_data: Optional[bytes] = None,
    image_content_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Schedule a Bluesky post (text + optional image) at a specific UTC datetime.
    
    Args:
        args: Dictionary with 'text' (str), 'when_utc' (ISO 8601 string),
              optional 'image_url' or 'image_bytes' (base64)
        bluesky_client: BlueskyClient instance
        image_data: Optional image bytes (if provided directly)
        image_content_type: Optional image content type
        
    Returns:
        Dictionary with 'task_id' (str), 'scheduled_for' (ISO string)
    """
    text = args.get("text", "")
    when_utc_str = args.get("when_utc", "")
    image_url = args.get("image_url")
    image_bytes_b64 = args.get("image_bytes")
    
    if not text or not when_utc_str:
        return {"error": "text and when_utc are required"}
    
    try:
        # Parse datetime - handle both Z and +00:00 formats
        when_utc_str_clean = when_utc_str.replace("Z", "+00:00")
        when_dt = datetime.fromisoformat(when_utc_str_clean)
        
        # Ensure timezone-aware (default to UTC if not specified)
        if when_dt.tzinfo is None:
            # Assume UTC if no timezone specified
            when_dt = when_dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC if different timezone
            when_dt = when_dt.astimezone(timezone.utc)
        
        # Validate future time
        now = datetime.now(timezone.utc)
        if when_dt <= now:
            # Provide helpful error message with current time
            error_msg = (
                f"Cannot schedule post in the past. "
                f"Requested: {when_dt.isoformat()}, "
                f"Current UTC: {now.isoformat()}. "
                f"Please use a FUTURE datetime relative to the current time."
            )
            log_event(
                source="dom_bot",
                event_type="scheduling_error_past_date",
                payload={
                    "requested": when_dt.isoformat(),
                    "current": now.isoformat(),
                    "text_preview": text[:100]
                }
            )
            return {"error": error_msg}
        
        # Handle image if provided
        final_image_data = image_data
        final_image_type = image_content_type or "image/jpeg"
        
        if image_bytes_b64 and not final_image_data:
            try:
                final_image_data = base64.b64decode(image_bytes_b64)
            except Exception as e:
                return {"error": f"Invalid base64 image data: {str(e)}"}
        
        # Create coroutine to post
        async def post_scheduled():
            try:
                if final_image_data:
                    # Upload blob first
                    blob_result = bluesky_client.upload_blob(final_image_data, final_image_type)
                    images = [{
                        "blob": blob_result.get("blob", {}),
                        "alt": text[:500]  # Use text as alt
                    }]
                    post_result = bluesky_client.create_image_post(text, images)
                else:
                    post_result = bluesky_client.post_message(text)
                
                log_event(
                    source="dom_bot",
                    event_type="scheduled_bsky_posted",
                    payload={
                        "text": text[:100],
                        "post_uri": post_result.get("uri", "unknown"),
                        "scheduled_for": when_dt.isoformat()
                    }
                )
            except Exception as e:
                log_error("dom_bot", e, {
                    "tool": "bsky_schedule_post",
                    "action": "post_scheduled"
                })
        
        # Schedule it
        scheduler = get_scheduler()
        # Store image as base64 for persistence
        image_b64 = None
        if final_image_data:
            import base64
            image_b64 = base64.b64encode(final_image_data).decode('utf-8')
        
        task_id = scheduler.schedule_at(
            when_dt,
            post_scheduled(),
            name="bsky_post",
            handler_type="bsky_schedule_post",
            parameters={
                "text": text,
                "image_bytes": image_b64,
                "image_content_type": final_image_type if final_image_data else None
            }
        )
        
        result = {
            "task_id": task_id,
            "scheduled_for": when_dt.isoformat(),
            "success": True,
            "has_image": final_image_data is not None
        }
        log_tool_call("bsky_schedule_post", args, result)
        return result
    except ValueError as e:
        return {"error": f"Invalid datetime format: {str(e)}"}
    except Exception as e:
        log_error("dom_bot", e, {"tool": "bsky_schedule_post", "args": args})
        return {"error": str(e)}


# Tool handler registry
TOOL_HANDLERS = {
    "memory_search": memory_search,
    "memory_upsert": memory_upsert,
    "discord_send_now": discord_send_now,
    "discord_schedule_message": discord_schedule_message,
    "bsky_schedule_post": bsky_schedule_post,
}


def register_scheduler_restore_handlers(
    scheduler,
    discord_bot=None,
    bluesky_client=None
) -> None:
    """
    Register restoration handlers for scheduler tasks.
    
    Args:
        scheduler: Scheduler instance
        discord_bot: DiscordBot instance (optional)
        bluesky_client: BlueskyClient instance (optional)
    """
    # Register Discord message restoration handler
    if discord_bot:
        async def restore_discord_message(parameters: Dict[str, Any]) -> None:
            """Restore a scheduled Discord message."""
            message = parameters.get("message", "")
            channel_id = parameters.get("channel_id", "")
            
            if message:
                try:
                    await discord_bot.send_message(message)
                    log_event(
                        source="scheduler",
                        event_type="restored_discord_message_sent",
                        payload={
                            "channel_id": channel_id,
                            "message": message[:100]
                        }
                    )
                except Exception as e:
                    log_error("scheduler", e, {
                        "action": "restore_discord_message",
                        "channel_id": channel_id
                    })
        
        scheduler.register_restore_handler("discord_schedule_message", restore_discord_message)
    
    # Register Bluesky post restoration handler
    if bluesky_client:
        async def restore_bsky_post(parameters: Dict[str, Any]) -> None:
            """Restore a scheduled Bluesky post."""
            text = parameters.get("text", "")
            image_bytes_b64 = parameters.get("image_bytes")
            image_content_type = parameters.get("image_content_type", "image/jpeg")
            
            if text:
                try:
                    image_data = None
                    if image_bytes_b64:
                        image_data = base64.b64decode(image_bytes_b64)
                    
                    if image_data:
                        # Upload blob first
                        blob_result = bluesky_client.upload_blob(image_data, image_content_type)
                        images = [{
                            "blob": blob_result.get("blob", {}),
                            "alt": text[:500]
                        }]
                        post_result = bluesky_client.create_image_post(text, images)
                    else:
                        post_result = bluesky_client.post_message(text)
                    
                    log_event(
                        source="scheduler",
                        event_type="restored_bsky_post_sent",
                        payload={
                            "text": text[:100],
                            "post_uri": post_result.get("uri", "unknown"),
                            "has_image": image_data is not None
                        }
                    )
                except Exception as e:
                    log_error("scheduler", e, {
                        "action": "restore_bsky_post"
                    })
        
        scheduler.register_restore_handler("bsky_schedule_post", restore_bsky_post)

