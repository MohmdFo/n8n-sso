import os
import urllib.parse
from conf.settings import get_settings
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

def get_casdoor_login_url(redirect_uri: str, state: str = "state") -> str:
    """Generate Casdoor OAuth login URL with proper parameters."""
    settings = get_settings()
    base_url = str(settings.CASDOOR_ENDPOINT).rstrip("/")
    
    params = {
        "client_id": settings.CASDOOR_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    
    query_string = urllib.parse.urlencode(params)
    login_url = f"{base_url}/login/oauth/authorize?{query_string}"
    
    logger.info("Generated Casdoor login URL", extra={
        "casdoor_endpoint": base_url,
        "client_id": settings.CASDOOR_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "state": state,
        "url_length": len(login_url)
    })
    
    return login_url
