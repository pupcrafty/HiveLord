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
        self.client: Optional[httpx.Client] = None
        self.session: Optional[Dict[str, Any]] = None
        self._initialized = False
    
    def is_enabled(self) -> bool:
        """Check if Bluesky client is enabled and has required configuration."""
        print("[BLUESKY DEBUG] Checking if Bluesky client is enabled...")
        if not self.settings.enable_bluesky:
            print("[BLUESKY DEBUG] Bluesky is disabled (enable_bluesky=False)")
            return False
        if not (self.settings.bsky_handle and self.settings.bsky_app_password):
            print("[BLUESKY DEBUG] Bluesky missing configuration (handle or app_password)")
            return False
        print(f"[BLUESKY DEBUG] Bluesky client is enabled and configured (handle: {self.settings.bsky_handle})")
        return True
    
    def _ensure_initialized(self) -> None:
        """Ensure client is initialized."""
        print("[BLUESKY DEBUG] Ensuring Bluesky client is initialized...")
        if not self._initialized:
            if not self.is_enabled():
                print("[BLUESKY DEBUG] ERROR: Bluesky client is not enabled or missing configuration")
                raise RuntimeError("Bluesky client is not enabled or missing configuration")
            print("[BLUESKY DEBUG] Creating HTTP client with 30s timeout...")
            self.client = httpx.Client(timeout=30.0)
            self._initialized = True
            print("[BLUESKY DEBUG] HTTP client created and initialized")
    
    def _get_pds_url(self) -> str:
        """Get the PDS base URL."""
        return self.settings.bsky_pds_host.rstrip('/')
    
    def create_session(self) -> Dict[str, Any]:
        """
        Create a Bluesky session (authenticate).
        
        Returns:
            Session information including accessJwt and refreshJwt
        """
        print("[BLUESKY DEBUG] ===== CREATING BLUESKY SESSION =====")
        self._ensure_initialized()
        url = f"{self._get_pds_url()}/xrpc/com.atproto.server.createSession"
        print(f"[BLUESKY DEBUG] PDS URL: {self._get_pds_url()}")
        print(f"[BLUESKY DEBUG] Session endpoint: {url}")
        print(f"[BLUESKY DEBUG] Handle: {self.settings.bsky_handle}")
        print(f"[BLUESKY DEBUG] App password length: {len(self.settings.bsky_app_password) if self.settings.bsky_app_password else 0}")
        
        payload = {
            "identifier": self.settings.bsky_handle,
            "password": self.settings.bsky_app_password
        }
        
        try:
            print("[BLUESKY DEBUG] Sending POST request to create session...")
            log_api_request("bluesky", "POST", url)
            response = self.client.post(url, json=payload)
            print(f"[BLUESKY DEBUG] Response received - Status: {response.status_code}")
            log_api_response("bluesky", response.status_code)
            
            # Check for HTTP errors and capture response details before raising
            try:
                response.raise_for_status()
                print("[BLUESKY DEBUG] HTTP status check passed")
            except httpx.HTTPStatusError as e:
                # Extract error details from response
                print(f"[BLUESKY DEBUG] ERROR: HTTP {response.status_code} - Authentication failed")
                error_detail = None
                try:
                    error_detail = response.json()
                    print(f"[BLUESKY DEBUG] Error response (JSON): {error_detail}")
                except Exception:
                    error_detail = {"text": response.text[:500] if response.text else "No response body"}
                    print(f"[BLUESKY DEBUG] Error response (text): {error_detail}")
                
                error_msg = (
                    f"Bluesky authentication failed: HTTP {response.status_code}. "
                    f"Response: {error_detail}"
                )
                print(f"[BLUESKY DEBUG] Logging error: {error_msg[:200]}")
                log_error("bluesky", error_msg, {
                    "action": "createSession",
                    "status_code": response.status_code,
                    "error_detail": error_detail
                })
                raise
            
            print("[BLUESKY DEBUG] Parsing response JSON...")
            self.session = response.json()
            print("[BLUESKY DEBUG] Session created successfully!")
            print(f"[BLUESKY DEBUG] Session has accessJwt: {'accessJwt' in self.session}")
            print(f"[BLUESKY DEBUG] Session has refreshJwt: {'refreshJwt' in self.session}")
            if 'did' in self.session:
                print(f"[BLUESKY DEBUG] User DID: {self.session.get('did')}")
            return self.session
        except httpx.HTTPStatusError as e:
            print(f"[BLUESKY DEBUG] HTTPStatusError raised: {type(e).__name__}")
            # Re-raise HTTPStatusError as-is (already logged above)
            raise
        except httpx.HTTPError as e:
            print(f"[BLUESKY DEBUG] HTTPError: {type(e).__name__}: {e}")
            log_error("bluesky", e, {
                "action": "createSession",
                "error_type": type(e).__name__
            })
            raise
        except Exception as e:
            print(f"[BLUESKY DEBUG] Unexpected error: {type(e).__name__}: {e}")
            log_error("bluesky", e, {
                "action": "createSession",
                "error_type": type(e).__name__
            })
            raise
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        print("[BLUESKY DEBUG] Getting auth headers...")
        if not self.session:
            print("[BLUESKY DEBUG] No session found, creating new session...")
            self.create_session()
        
        access_jwt = self.session.get("accessJwt") if self.session else None
        if not access_jwt:
            print("[BLUESKY DEBUG] ERROR: No accessJwt in session")
            raise ValueError("No session token available")
        
        print("[BLUESKY DEBUG] Auth headers created successfully")
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
        print(f"[BLUESKY DEBUG] ===== CREATING RECORD =====")
        print(f"[BLUESKY DEBUG] Text preview: {text[:50]}...")
        self._ensure_initialized()
        if not repo:
            repo = self.settings.bsky_handle
        print(f"[BLUESKY DEBUG] Repository: {repo}")
        
        url = f"{self._get_pds_url()}/xrpc/com.atproto.repo.createRecord"
        print(f"[BLUESKY DEBUG] Create record URL: {url}")
        
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
        print(f"[BLUESKY DEBUG] Payload prepared (collection: {collection})")
        
        try:
            print("[BLUESKY DEBUG] Sending POST request to create record...")
            log_api_request("bluesky", "POST", url)
            headers = self._get_auth_headers()
            response = self.client.post(
                url,
                json=payload,
                headers=headers
            )
            print(f"[BLUESKY DEBUG] Response received - Status: {response.status_code}")
            log_api_response("bluesky", response.status_code)
            
            response.raise_for_status()
            result = response.json()
            print("[BLUESKY DEBUG] Record created successfully!")
            return result
        except httpx.HTTPError as e:
            print(f"[BLUESKY DEBUG] ERROR creating record: {type(e).__name__}: {e}")
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
        print("[BLUESKY DEBUG] Closing Bluesky client...")
        if self.client:
            print("[BLUESKY DEBUG] Closing HTTP client connection...")
            self.client.close()
            self.client = None
            self._initialized = False
            print("[BLUESKY DEBUG] HTTP client closed")
        else:
            print("[BLUESKY DEBUG] No client instance to close")

