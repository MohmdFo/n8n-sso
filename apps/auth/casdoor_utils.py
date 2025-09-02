import os
import urllib.parse
from conf.settings import get_settings

def get_casdoor_login_url(redirect_uri: str, state: str = "state") -> str:
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
    return f"{base_url}/login/oauth/authorize?{query_string}"
