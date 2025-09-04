"""Casdoor callback orchestration for n8n SSO."""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from backup.auth.services import (
    get_oauth_token,
    parse_jwt_token,
)
from apps.integrations.n8n_db import (
    CasdoorProfile, 
    ensure_user_project_binding, 
    rotate_user_password
)
from apps.integrations.n8n_client import N8NClient
from conf.settings import get_settings

logger = logging.getLogger(__name__)

def extract_n8n_auth_cookie(response) -> str | None:
    """Extract n8n-auth cookie from httpx Response."""
    if not response:
        return None
        
    # Check if response has cookies attribute (httpx Response)
    if hasattr(response, 'cookies') and response.cookies:
        auth_cookie = response.cookies.get('n8n-auth')
        if auth_cookie:
            return auth_cookie
    
    # Check set-cookie headers
    if hasattr(response, 'headers'):
        set_cookie_headers = response.headers.get_list('set-cookie') or []
        for cookie in set_cookie_headers:
            if 'n8n-auth=' in cookie:
                # Extract cookie value (everything between n8n-auth= and the next ;)
                cookie_value = cookie.split('n8n-auth=')[1].split(';')[0]
                return cookie_value
                
        # Also check single set-cookie header if get_list didn't work
        single_cookie = response.headers.get('set-cookie')
        if single_cookie and 'n8n-auth=' in single_cookie:
            cookie_value = single_cookie.split('n8n-auth=')[1].split(';')[0]
            return cookie_value
    
    return None

def map_casdoor_to_profile(user_info: Dict[str, Any]) -> CasdoorProfile:
    """Map Casdoor JWT claims to CasdoorProfile."""
    email = (
        user_info.get("email") 
        or user_info.get("mail") 
        or user_info.get("preferred_username")
    )
    if not email:
        raise ValueError("Casdoor profile missing email")
    
    name = user_info.get("name") or user_info.get("display_name") or ""
    first_name = user_info.get("given_name")
    last_name = user_info.get("family_name")
    
    # Split name if first/last not provided separately
    if not first_name and name:
        name_parts = name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    return CasdoorProfile(
        email=email,
        first_name=first_name,
        last_name=last_name,
        display_name=name,
        casdoor_id=user_info.get("sub") or user_info.get("id"),
        avatar_url=user_info.get("picture") or user_info.get("avatar")
    )

async def handle_casdoor_callback(request: Request) -> RedirectResponse:
    """Handle Casdoor OAuth callback and redirect to n8n with session."""
    request_id = str(uuid.uuid4())[:8]
    logger.info("Processing Casdoor callback", extra={"request_id": request_id})
    
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # TODO: Validate state (retrieve from session/cache for CSRF protection)
    
    try:
        # 1. Exchange code for tokens via existing helper
        token_info = get_oauth_token(code)
        id_token = token_info.get("id_token")
        if not id_token:
            raise HTTPException(status_code=400, detail="Token response missing id_token")

        # 2. Parse and verify JWT token
        user_info = parse_jwt_token(id_token)
        
        # 3. Map to CasdoorProfile
        profile = map_casdoor_to_profile(user_info)
        
        logger.info("Casdoor user authenticated", extra={
            "request_id": request_id,
            "email": profile.email,
            "casdoor_id": profile.casdoor_id
        })
        
    except Exception as exc:
        logger.exception("Failed to process Casdoor token", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail=f"Invalid token: {exc}")

    try:
        settings = get_settings()
        
        # 4. Ensure user/project/relation in n8n database
        user_row, project_row, temp_password = await ensure_user_project_binding(
            profile,
            global_role=settings.N8N_DEFAULT_GLOBAL_ROLE,
            project_role=settings.N8N_DEFAULT_PROJECT_ROLE
        )
        
        logger.info("n8n user/project ensured", extra={
            "request_id": request_id,
            "email": profile.email,
            "user_id": str(user_row.id),
            "project_id": project_row.id,
            "is_new_user": temp_password is not None
        })
        
        # 5. Handle password for login
        if temp_password is None:
            # Existing user - rotate password for this session
            temp_password = secrets.token_urlsafe(32)
            await rotate_user_password(user_row.id, temp_password)
            logger.info("Rotated password for existing user", extra={
                "request_id": request_id,
                "user_id": str(user_row.id)
            })
        
        # 6. Login to n8n to get session cookie and extract it
        n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
        auth_cookie = None
        
        try:
            logger.info("Attempting n8n login", extra={
                "request_id": request_id,
                "email": profile.email,
                "password_length": len(temp_password)
            })
            login_response = n8n_client.login_user(profile.email, temp_password)
            
            # Extract the n8n-auth cookie from the login response
            auth_cookie = extract_n8n_auth_cookie(login_response)
            
            logger.info("n8n login result", extra={
                "request_id": request_id,
                "email": profile.email,
                "status_code": getattr(login_response, 'status_code', 'unknown'),
                "has_auth_cookie": auth_cookie is not None,
                "cookie_length": len(auth_cookie) if auth_cookie else 0,
                "response_headers": dict(getattr(login_response, 'headers', {}))
            })
            
        except Exception as login_exc:
            logger.error("n8n login failed", extra={
                "request_id": request_id,
                "email": profile.email,
                "error": str(login_exc)
            })
            # auth_cookie remains None, will fall back to form submission
        finally:
            n8n_client.close()
        
        # 7. Create redirect response with cookie setting
        n8n_base_url = str(settings.N8N_BASE_URL).rstrip('/')
        n8n_workflows_url = f"{n8n_base_url}/home/workflows"
        
        if auth_cookie:
            # For local development, the cookie method won't work due to domain mismatch
            # In production, this should work when deployed on same domain as n8n
            
            # Check if we're in local development mode
            import os
            is_local = os.getenv("DEBUG", "false").lower() == "true"
            
            if is_local:
                logger.info("Local development mode - using form fallback", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "reason": "domain_mismatch_localhost"
                })
                # Don't use the cookie method in local dev - fall through to form method
                auth_cookie = None
            else:
                # Production mode - use cookie method
                logger.info("Production mode - using cookie method", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "redirect_url": n8n_workflows_url,
                    "cookie_length": len(auth_cookie)
                })
                
                from urllib.parse import urlparse
                parsed_url = urlparse(n8n_base_url)
                cookie_domain = parsed_url.hostname
                is_secure = parsed_url.scheme == "https"
                
                response = RedirectResponse(url=n8n_workflows_url, status_code=302)
                
                # Set the n8n-auth cookie
                response.set_cookie(
                    key="n8n-auth",
                    value=auth_cookie,
                    domain=cookie_domain,
                    path="/",
                    httponly=True,
                    secure=is_secure,
                    samesite="lax",
                    max_age=7 * 24 * 3600  # 7 days
                )
                
                logger.info("Cookie set, redirecting to n8n", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "cookie_domain": cookie_domain
                })
                
                return response
        
        # Method 2: Fallback to form submission (works for local development)
        if auth_cookie is None:
            n8n_login_url = f"{n8n_base_url}/rest/login"
            
            logger.info("Falling back to form submission method", extra={
                "request_id": request_id,
                "email": profile.email,
                "n8n_login_url": n8n_login_url
            })
            
            # Create an HTML auto-submit form that will log the user into n8n
            handoff_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Logging you into n8n...</title>
                <meta charset="utf-8">
                <script>
                    // Try to handle the response and redirect
                    function handleLoginResponse() {{
                        // After successful login, redirect to workflows
                        setTimeout(function() {{
                            window.location.href = '{n8n_workflows_url}';
                        }}, 1000);
                    }}
                </script>
            </head>
            <body onload="handleLoginResponse()">
                <div style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
                    <h2>🔐 Completing your login...</h2>
                    <p>You will be redirected to n8n in a moment.</p>
                    <div style="margin: 20px;">
                        <div style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                    </div>
                </div>
                
                <form id="loginForm" method="POST" action="{n8n_login_url}" style="display: none;">
                    <input type="hidden" name="emailOrLdapLoginId" value="{profile.email}">
                    <input type="hidden" name="password" value="{temp_password}">
                </form>
                
                <script>
                    document.getElementById('loginForm').submit();
                </script>
                
                <style>
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </body>
            </html>
            """
            
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=handoff_html, status_code=200)
        
    except Exception as exc:
        logger.exception("Failed to provision/login to n8n", extra={
            "request_id": request_id,
            "email": profile.email if 'profile' in locals() else "unknown"
        })
        raise HTTPException(status_code=502, detail="Upstream n8n error")
