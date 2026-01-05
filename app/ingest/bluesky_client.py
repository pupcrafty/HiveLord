"""Bluesky AT Protocol client."""
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import httpx

from app.config.settings import get_settings
from app.core.logger import log_api_request, log_api_response, log_error


class BlueskyClient:
    """Bluesky AT Protocol client."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.Client(timeout=30.0)
        self.session: Optional[Dict[str, Any]] = None
    
    def _get_pds_url(self) -> str:
        """Get the PDS base URL."""
        return self.settings.bsky_pds_host.rstrip('/')
    
    def create_session(self) -> Dict[str, Any]:
        """
        Create a Bluesky session (authenticate).
        
        Returns:
            Session information including accessJwt and refreshJwt
        """
        url = f"{self._get_pds_url()}/xrpc/com.atproto.server.createSession"
        
        payload = {
            "identifier": self.settings.bsky_handle,
            "password": self.settings.bsky_app_password
        }
        
        try:
            log_api_request("bluesky", "POST", url)
            response = self.client.post(url, json=payload)
            log_api_response("bluesky", response.status_code)
            
            response.raise_for_status()
            self.session = response.json()
            return self.session
        except httpx.HTTPError as e:
            log_error("bluesky", e, {"action": "createSession"})
            raise
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        if not self.session:
            self.create_session()
        
        access_jwt = self.session.get("accessJwt") if self.session else None
        if not access_jwt:
            raise ValueError("No session token available")
        
        return {
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": "application/json"
        }
    
    def create_record(self, text: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a post (record) on Bluesky.
        
        Args:
            text: Post text content
            repo: Repository (handle), defaults to settings handle
            
        Returns:
            Created record information
        """
        if not repo:
            repo = self.settings.bsky_handle
        
        url = f"{self._get_pds_url()}/xrpc/com.atproto.repo.createRecord"
        
        # Format: at://did:plc:xxx/APP.BSky.Feed.Post/xxx
        # For now, we'll use the handle directly
        collection = "app.bsky.feed.post"
        
        payload = {
            "repo": repo,
            "collection": collection,
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }
        }
        
        try:
            log_api_request("bluesky", "POST", url)
            response = self.client.post(
                url,
                json=payload,
                headers=self._get_auth_headers()
            )
            log_api_response("bluesky", response.status_code)
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            log_error("bluesky", e, {"action": "createRecord", "text_preview": text[:50]})
            raise
    
    def post_message(self, text: str) -> Dict[str, Any]:
        """
        Post a message to Bluesky (convenience method).
        
        Args:
            text: Message text
            
        Returns:
            Created post information
        """
        return self.create_record(text)
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

