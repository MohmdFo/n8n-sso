"""Minimal n8n REST client for session management."""
from __future__ import annotations

import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0

class N8NClientError(RuntimeError):
    def __init__(self, status: int, message: str, payload: Any | None = None):
        super().__init__(f"n8n API error {status}: {message}")
        self.status = status
        self.payload = payload

class N8NClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip('/')
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=False)

    def _headers(self) -> Dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def login_user(self, email: str, password: str) -> httpx.Response:
        """Login user and return raw response with Set-Cookie headers."""
        payload = {"emailOrLdapLoginId": email, "password": password}
        resp = self._client.request(
            "POST", 
            "/rest/login", 
            json=payload, 
            headers=self._headers()
        )
        
        if resp.status_code >= 400:
            logger.error("n8n login failed", extra={
                "status": resp.status_code,
                "email": email,
                "response_text": resp.text[:500],  # Truncate response
                "response_headers": dict(resp.headers)
            })
            raise N8NClientError(resp.status_code, "Login failed", resp.text)
        
        logger.info("n8n login successful", extra={
            "email": email, 
            "status": resp.status_code,
            "cookies": [cookie for cookie in resp.headers.get_list("set-cookie") or []],
            "response_text": resp.text[:200],  # First 200 chars of response
            "all_headers": dict(resp.headers)
        })
        return resp

    def logout_user(self, auth_cookie: str = None) -> httpx.Response:
        """Logout user from n8n by calling the logout endpoint."""
        headers = self._headers()
        
        # If we have an auth cookie, include it in the request
        if auth_cookie:
            headers["Cookie"] = f"n8n-auth={auth_cookie}"
        
        try:
            resp = self._client.request(
                "POST", 
                "/rest/logout", 
                headers=headers
            )
            
            logger.info("n8n logout attempt", extra={
                "status": resp.status_code,
                "has_auth_cookie": auth_cookie is not None,
                "response_text": resp.text[:200] if resp.text else "no response",
                "response_headers": dict(resp.headers)
            })
            
            return resp
            
        except Exception as exc:
            logger.error("n8n logout failed", extra={
                "error": str(exc),
                "has_auth_cookie": auth_cookie is not None
            })
            raise N8NClientError(500, f"Logout request failed: {exc}")

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
