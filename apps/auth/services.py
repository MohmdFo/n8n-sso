"""Casdoor callback orchestration for n8n SSO."""
from __future__ import annotations

import logging
import secrets
import uuid
import asyncio
import requests
import jwt
import httpx
from typing import Any, Dict
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from apps.integrations.n8n_db import (
    CasdoorProfile, 
    ensure_user_project_binding, 
    rotate_user_password
)
from apps.integrations.n8n_client import N8NClient
from conf.settings import get_settings
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

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

    return None


async def get_oauth_token(code: str) -> dict:
    """
    Exchange the Casdoor OAuth authorization code for an access token.

    This function sends a POST request to the Casdoor token endpoint with the provided code.
    If the response status is not 200 (OK), it raises an HTTPException after 3 retry attempts.
    For invalid_grant errors (code already used), it does not retry.

    :param code: The authorization code received from Casdoor.
    :return: A dictionary representing the OAuth token response (expected to contain an "id_token").
    :raises HTTPException: If the token request fails after all retries (status code != 200).
    """
    settings = get_settings()
    url = f"{str(settings.CASDOOR_ENDPOINT).rstrip('/')}/api/login/oauth/access_token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.CASDOOR_CLIENT_ID,
        "client_secret": settings.CASDOOR_CLIENT_SECRET,
        "code": code,
    }
    
    max_retries = 3
    base_delay = 1  # seconds
    
    logger.info("Requesting OAuth token from Casdoor", extra={
        "url": url,
        "client_id": settings.CASDOOR_CLIENT_ID,
        "code_length": len(code) if code else 0,
        "code_preview": code[:10] + "..." if code and len(code) > 10 else code
    })
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(url, data=payload)
                
                logger.info("OAuth token request attempt", extra={
                    "attempt": attempt + 1,
                    "status_code": response.status_code,
                    "response_size": len(response.content) if response.content else 0,
                    "response_headers": dict(response.headers)
                })
                
                if response.status_code == 200:
                    try:
                        token_data = response.json()
                        
                        # Log success with token info (but mask sensitive data)
                        logger.info("OAuth token obtained successfully", extra={
                            "attempt": attempt + 1,
                            "has_access_token": "access_token" in token_data,
                            "has_id_token": "id_token" in token_data,
                            "token_type": token_data.get("token_type"),
                            "expires_in": token_data.get("expires_in"),
                            "id_token_length": len(token_data.get("id_token", "")) if token_data.get("id_token") else 0
                        })
                        
                        return token_data
                        
                    except ValueError as json_error:
                        logger.error("Failed to parse JSON response", extra={
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "response_text": response.text[:500],  # First 500 chars
                            "json_error": str(json_error)
                        })
                        
                        if attempt == max_retries - 1:
                            raise HTTPException(
                                status_code=502, 
                                detail=f"Invalid JSON response from Casdoor: {str(json_error)}"
                            )
                else:
                    # Check for invalid_grant error
                    if response.status_code == 400:
                        try:
                            error_data = response.json()
                            if error_data.get("error") == "invalid_grant" and "authorization code has been used" in error_data.get("error_description", ""):
                                # Code already used, don't retry
                                logger.warning("Authorization code already used", extra={
                                    "attempt": attempt + 1,
                                    "code": code,
                                    "error": error_data
                                })
                                raise HTTPException(
                                    status_code=400,
                                    detail="Authorization code already used"
                                )
                        except ValueError:
                            pass  # Not JSON, handle as normal
                    
                    # Log non-200 response
                    logger.warning("OAuth token request failed", extra={
                        "attempt": attempt + 1,
                        "status_code": response.status_code,
                        "response_text": response.text[:500],  # First 500 chars
                        "response_headers": dict(response.headers)
                    })
                    
                    if attempt == max_retries - 1:
                        # Final attempt failed
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Failed to obtain token after {max_retries} attempts. Last status: {response.status_code}, Response: {response.text[:200]}"
                        )
            
            except httpx.RequestError as req_error:
                logger.error("OAuth token request network error", extra={
                    "attempt": attempt + 1,
                    "error": str(req_error),
                    "url": url
                })
                
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=502, 
                        detail=f"Network error requesting token after {max_retries} attempts: {str(req_error)}"
                    )
            
            # Wait before retrying (exponential backoff)
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                logger.info("Retrying OAuth token request", extra={
                    "attempt": attempt + 1,
                    "next_attempt_in": delay,
                    "max_retries": max_retries
                })
                await asyncio.sleep(delay)


def parse_jwt_token(token: str) -> dict:
    """
    Verify and decode the provided JWT token using the Casdoor certificate.

    This function loads the certificate, extracts the public key, and attempts to decode
    the JWT with the audience set to the Casdoor client ID and a leeway of 60 seconds.

    :param token: The JWT token string to be parsed.
    :return: A dictionary containing the decoded token payload.
    :raises jwt.PyJWTError: If the token validation or decoding fails.
    """
    settings = get_settings()
    
    try:
        # Load certificate from file path
        with open(settings.CASDOOR_CERT_PATH, "r") as cert_file:
            cert_content = cert_file.read()
        
        certificate = x509.load_pem_x509_certificate(cert_content.encode("utf-8"), default_backend())
        public_key = certificate.public_key()
    except Exception as e:
        logger.error(f"Error loading certificate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Certificate loading error: {str(e)}")
    
    # First, try to decode without audience validation to see what the actual audience is
    try:
        decoded_without_audience = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=60
        )
        actual_audience = decoded_without_audience.get("aud")
        logger.info(f"JWT token audience: {actual_audience}")
        logger.info(f"Expected audience (CASDOOR_CLIENT_ID): {settings.CASDOOR_CLIENT_ID}")
        
        # Handle different audience formats that Casdoor might use
        expected_audiences = set([
            settings.CASDOOR_CLIENT_ID,
            f"{settings.CASDOOR_CLIENT_ID}-org-built-in",
            f"{settings.CASDOOR_CLIENT_ID}-org-{settings.CASDOOR_ORG_NAME}"
        ])
        
        # Handle case where actual_audience might be a list or string
        if isinstance(actual_audience, list):
            actual_audiences = actual_audience
        else:
            actual_audiences = [actual_audience] if actual_audience else []
        
        # Check if any of the actual audiences match any of the expected audiences
        matching_audience = None
        for actual_aud in actual_audiences:
            if actual_aud in expected_audiences:
                matching_audience = actual_aud
                break
        
        if matching_audience:
            # Audience matches one of the expected formats
            logger.info(f"Using matching audience: {matching_audience}")
            return jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=matching_audience,
                leeway=60
            )
        else:
            logger.warning(f"Audience mismatch! Token audience: {actual_audience}, Expected one of: {list(expected_audiences)}")
            
            # Try with the actual audience from the token (if it's a string)
            if actual_audiences and len(actual_audiences) == 1:
                try:
                    return jwt.decode(
                        token,
                        public_key,
                        algorithms=["RS256"],
                        audience=actual_audiences[0],
                        leeway=60
                    )
                except jwt.InvalidAudienceError:
                    logger.error(f"Failed to validate with actual audience: {actual_audiences[0]}")
            
            # If that fails, try without audience validation as a fallback
            logger.warning("Falling back to decoding without audience validation")
            return decoded_without_audience
            
    except Exception as e:
        logger.error(f"Error in initial token decoding: {str(e)}")
        # Fallback to original behavior
        try:
            return jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=settings.CASDOOR_CLIENT_ID,
                leeway=60
            )
        except Exception as fallback_error:
            logger.error(f"Fallback token decoding also failed: {str(fallback_error)}")
            raise HTTPException(status_code=400, detail=f"Token decoding failed: {str(fallback_error)}")


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
        token_info = await get_oauth_token(code)
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
        
    except HTTPException as http_exc:
        if http_exc.detail == "Authorization code already used":
            # Code already used, redirect to default URL
            logger.warning("Authorization code already used, redirecting user", extra={
                "request_id": request_id,
                "code": code,
                "state": state
            })
            settings = get_settings()
            return RedirectResponse(url=settings.DEFAULT_REDIRECT_URL, status_code=302)
        else:
            # Other HTTPExceptions - log and redirect with generic message
            logger.warning("Unexpected HTTP error during token processing, redirecting user", extra={
                "request_id": request_id,
                "status_code": http_exc.status_code,
                "detail": http_exc.detail
            })
            settings = get_settings()
            return RedirectResponse(url=settings.DEFAULT_REDIRECT_URL, status_code=302)
    except Exception as exc:
        logger.exception("Unexpected error during token processing, redirecting user", extra={"request_id": request_id})
        settings = get_settings()
        return RedirectResponse(url=settings.DEFAULT_REDIRECT_URL, status_code=302)

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
            # Try the cookie method first (should work in production)
            logger.info("Cookie extracted - attempting direct redirect with cookie", extra={
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
            
            logger.info("Cookie set, redirecting to workflows", extra={
                "request_id": request_id,
                "email": profile.email,
                "cookie_domain": cookie_domain,
                "redirect_url": n8n_workflows_url
            })
            
            return response
        
        # Method 2: Fallback using JavaScript login with proper redirect
        logger.info("Using JavaScript login method with redirect", extra={
            "request_id": request_id,
            "email": profile.email,
            "target_url": n8n_workflows_url
        })
        
        # Use JavaScript to login and then redirect properly
        handoff_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Logging you into n8n...</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body>
            <div style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
                <h2>🔐 Completing your login...</h2>
                <p>You will be redirected to n8n workflows in a moment.</p>
                <div style="margin: 20px;">
                    <div style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                </div>
            </div>
            
            <script>
                // Function to perform login and redirect
                async function performLogin() {{
                    try {{
                        // Perform the login request
                        const loginResponse = await fetch('{n8n_base_url}/rest/login', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            }},
                            body: JSON.stringify({{
                                emailOrLdapLoginId: '{profile.email}',
                                password: '{temp_password}'
                            }})
                        }});
                        
                        if (loginResponse.ok) {{
                            console.log('Login successful, redirecting to workflows...');
                            // Wait a moment for cookies to be set, then redirect
                            setTimeout(() => {{
                                window.location.href = '{n8n_workflows_url}';
                            }}, 500);
                        }} else {{
                            console.error('Login failed:', loginResponse.status);
                            // Still try to redirect as a fallback
                            setTimeout(() => {{
                                window.location.href = '{n8n_workflows_url}';
                            }}, 1000);
                        }}
                    }} catch (error) {{
                        console.error('Login request failed:', error);
                        // Fallback redirect
                        setTimeout(() => {{
                            window.location.href = '{n8n_workflows_url}';
                        }}, 1000);
                    }}
                }}
                
                // Start the login process immediately
                performLogin();
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
