"""Instagram Graph API client (read-only for wiring phase)."""
from typing import Dict, Any, Optional

import httpx

from app.config.settings import get_settings
from app.core.logger import log_api_request, log_api_response, log_error


class InstagramClient:
    """Instagram Graph API client."""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.Client(timeout=30.0)
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an API request with logging."""
        url = f"{self.BASE_URL}{endpoint}"
        
        if params is None:
            params = {}
        
        params["access_token"] = self.settings.ig_long_lived_access_token
        
        try:
            log_api_request("instagram", method, url)
            response = self.client.request(method, url, params=params)
            log_api_response("instagram", response.status_code)
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            log_error("instagram", e, {"method": method, "endpoint": endpoint})
            raise
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        Fetch basic account info.
        
        Returns:
            Account information from Instagram Graph API
        """
        return self._make_request(
            "GET",
            f"/{self.settings.ig_ig_user_id}",
            params={
                "fields": "id,username,account_type,media_count"
            }
        )
    
    def get_recent_media(self, limit: int = 10) -> Dict[str, Any]:
        """
        Fetch recent media metadata.
        
        Args:
            limit: Maximum number of media items to fetch
            
        Returns:
            Media information from Instagram Graph API
        """
        return self._make_request(
            "GET",
            f"/{self.settings.ig_ig_user_id}/media",
            params={
                "fields": "id,caption,media_type,media_url,timestamp,like_count,comments_count",
                "limit": limit
            }
        )
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

