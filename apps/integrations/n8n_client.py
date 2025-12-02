"""n8n API client for authentication and user management."""
from __future__ import annotations

import httpx
import logging
from typing import Dict, Any
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

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

    def logout_user_by_email(self, user_email: str) -> httpx.Response:
        """
        Logout a user by email. Since n8n doesn't have a direct API for this,
        we'll login as the user first to get a valid session, then logout.
        """
        try:
            # Import here to avoid circular imports
            from apps.integrations.n8n_db import get_user_by_email
            from conf.settings import get_settings
            import asyncio
            
            # Get user info from database
            async def get_user_password():
                user_row = await get_user_by_email(user_email)
                if not user_row:
                    raise N8NClientError(404, f"User not found: {user_email}")
                return user_row.password
            
            # Get the user's password from the database
            try:
                user_password = asyncio.run(get_user_password())
            except Exception as db_exc:
                logger.error("Failed to get user password from database", extra={
                    "user_email": user_email,
                    "error": str(db_exc)
                })
                # Fallback to general logout without specific user authentication
                return self.logout_user()
            
            # Step 1: Login as the user to get a valid session token
            logger.info("Attempting to login user for logout", extra={
                "user_email": user_email
            })
            
            try:
                login_resp = self.login_user(user_email, user_password)
                
                # Extract the auth cookie from login response
                auth_cookie = None
                if hasattr(login_resp, 'cookies') and login_resp.cookies:
                    auth_cookie = login_resp.cookies.get('n8n-auth')
                
                if not auth_cookie and hasattr(login_resp, 'headers'):
                    # Try to extract from set-cookie headers
                    set_cookie_headers = login_resp.headers.get_list('set-cookie') or []
                    for cookie in set_cookie_headers:
                        if 'n8n-auth=' in cookie:
                            auth_cookie = cookie.split('n8n-auth=')[1].split(';')[0]
                            break
                
                logger.info("Login for logout completed", extra={
                    "user_email": user_email,
                    "login_status": login_resp.status_code,
                    "has_auth_cookie": auth_cookie is not None
                })
                
                # Step 2: Now logout using the obtained auth cookie
                if auth_cookie:
                    logout_resp = self.logout_user(auth_cookie)
                    logger.info("User logout with auth cookie completed", extra={
                        "user_email": user_email,
                        "logout_status": logout_resp.status_code,
                        "approach": "login_then_logout"
                    })
                    return logout_resp
                else:
                    # Fallback: try logout without cookie
                    logout_resp = self.logout_user()
                    logger.warning("User logout without auth cookie", extra={
                        "user_email": user_email,
                        "logout_status": logout_resp.status_code,
                        "approach": "fallback_logout"
                    })
                    return logout_resp
                    
            except Exception as login_exc:
                logger.error("Login for logout failed", extra={
                    "user_email": user_email,
                    "error": str(login_exc)
                })
                # Fallback to general logout
                return self.logout_user()
            
        except Exception as exc:
            logger.error("Logout by email failed", extra={
                "user_email": user_email,
                "error": str(exc)
            })
            raise N8NClientError(500, f"Logout by email failed: {exc}")

    def import_workflow(self, workflow_data: dict, auth_cookie: str = None) -> httpx.Response:
        """Import a workflow to n8n."""
        headers = self._headers()
        
        # Add authentication cookie if provided
        if auth_cookie:
            headers["Cookie"] = f"n8n-auth={auth_cookie}"
        
        try:
            resp = self._client.request(
                "POST",
                "/rest/workflows",
                json=workflow_data,
                headers=headers
            )
            
            if resp.status_code >= 400:
                logger.error("n8n workflow import failed", extra={
                    "status": resp.status_code,
                    "response_text": resp.text[:500],
                    "workflow_name": workflow_data.get("name", "unknown")
                })
                raise N8NClientError(resp.status_code, "Workflow import failed", resp.text)
            
            logger.info("n8n workflow import successful", extra={
                "status": resp.status_code,
                "workflow_name": workflow_data.get("name", "unknown"),
                "workflow_id": resp.json().get("id") if resp.status_code < 400 else None
            })
            return resp
            
        except Exception as exc:
            logger.error("n8n workflow import failed", extra={
                "error": str(exc),
                "workflow_name": workflow_data.get("name", "unknown")
            })
            raise N8NClientError(500, f"Workflow import request failed: {exc}")

    def get_workflows(self, auth_cookie: str = None) -> httpx.Response:
        """Get list of workflows from n8n."""
        headers = self._headers()
        
        # Add authentication cookie if provided
        if auth_cookie:
            headers["Cookie"] = f"n8n-auth={auth_cookie}"
        
        try:
            resp = self._client.request(
                "GET",
                "/rest/workflows",
                headers=headers
            )
            
            if resp.status_code >= 400:
                logger.error("n8n get workflows failed", extra={
                    "status": resp.status_code,
                    "response_text": resp.text[:500]
                })
                raise N8NClientError(resp.status_code, "Get workflows failed", resp.text)
            
            return resp
            
        except Exception as exc:
            logger.error("n8n get workflows failed", extra={
                "error": str(exc)
            })
            raise N8NClientError(500, f"Get workflows request failed: {exc}")

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
