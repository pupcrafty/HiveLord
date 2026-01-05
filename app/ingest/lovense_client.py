"""Lovense Events API client (events only, no commands in wiring phase)."""
import asyncio
import json
import threading
from typing import Callable, Optional

import httpx
import websockets

from app.config.settings import get_settings
from app.core.logger import log_event, log_error


class LovenseClient:
    """Lovense Events API client - events only, no commands."""
    
    EVENTS_API_URL = "wss://api.lovense.com/api/lan/getQrId"
    
    def __init__(self):
        self.settings = get_settings()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._event_callbacks: list[Callable] = []
    
    def is_enabled(self) -> bool:
        """Check if Lovense client is enabled and has required configuration."""
        if not self.settings.enable_lovense:
            return False
        return bool(
            self.settings.lovense_developer_token and 
            self.settings.lovense_callback_url
        )
    
    def add_event_callback(self, callback: Callable) -> None:
        """Add a callback for events."""
        self._event_callbacks.append(callback)
    
    def _handle_event(self, event_data: dict) -> None:
        """Handle an incoming event."""
        log_event(
            source="lovense",
            event_type="event_received",
            payload=event_data
        )
        
        # Call registered callbacks
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    # Schedule in event loop if available
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(callback(event_data))
                        else:
                            loop.run_until_complete(callback(event_data))
                    except RuntimeError:
                        # No event loop, skip async callback
                        pass
                else:
                    callback(event_data)
            except Exception as e:
                log_error("lovense", e, {"callback_error": True})
    
    async def _connect_websocket(self) -> None:
        """Connect to Lovense Events API WebSocket."""
        if not self.is_enabled():
            raise RuntimeError("Lovense client is not enabled or missing configuration")
        
        try:
            # Note: Lovense Events API requires proper authentication
            # This is a simplified connection flow for wiring phase
            # Actual implementation will need proper auth flow
            
            url = f"{self.EVENTS_API_URL}?token={self.settings.lovense_developer_token}"
            
            log_event(
                source="lovense",
                event_type="connection_attempt",
                payload={"url": url.replace(self.settings.lovense_developer_token, "***")}
            )
            
            async with websockets.connect(url) as ws:
                self.ws = ws
                log_event(
                    source="lovense",
                    event_type="connected",
                    payload={"message": "WebSocket connected"}
                )
                
                # Listen for messages
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self._handle_event(data)
                    except json.JSONDecodeError as e:
                        log_error("lovense", e, {"raw_message": str(message)[:100]})
                    except Exception as e:
                        log_error("lovense", e, {"message_processing_error": True})
        
        except websockets.exceptions.ConnectionClosed:
            log_event(
                source="lovense",
                event_type="connection_closed",
                payload={"message": "WebSocket connection closed"}
            )
        except Exception as e:
            log_error("lovense", e, {"connection_error": True})
        finally:
            self.ws = None
    
    def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.thread.start()
    
    def _run_websocket(self) -> None:
        """Run the WebSocket connection."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connect_websocket())
        except Exception as e:
            log_error("lovense", e, {"websocket_thread_error": True})
        finally:
            self.running = False
    
    def stop(self) -> None:
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            # Close websocket in its event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.ws.close())
            except RuntimeError:
                pass
        
        if self.thread:
            self.thread.join(timeout=2.0)
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws is not None and not self.ws.closed

