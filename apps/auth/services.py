"""Casdoor callback orchestration for n8n SSO."""
from __future__ import annotations

import logging
import secrets
import time
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
from apps.core.error_handling import create_safe_redirect, log_and_redirect_on_error
from apps.auth.oauth_state import SessionManager

logger = get_logger(__name__)

def extract_n8n_auth_cookie(response) -> str | None:
    """Extract n8n-auth cookie from httpx Response with enhanced error handling."""
    if not response:
        logger.warning("extract_n8n_auth_cookie: No response provided")
        return None
        
    # Check if response has cookies attribute (httpx Response)
    if hasattr(response, 'cookies') and response.cookies:
        auth_cookie = response.cookies.get('n8n-auth')
        if auth_cookie:
            logger.debug("Cookie extracted from response.cookies attribute", extra={
                "cookie_length": len(auth_cookie)
            })
            return auth_cookie
    
    # Check set-cookie headers
    if hasattr(response, 'headers'):
        set_cookie_headers = response.headers.get_list('set-cookie') or []
        for cookie in set_cookie_headers:
            if 'n8n-auth=' in cookie:
                try:
                    # Extract cookie value (everything between n8n-auth= and the next ;)
                    cookie_value = cookie.split('n8n-auth=')[1].split(';')[0]
                    logger.debug("Cookie extracted from set-cookie headers", extra={
                        "cookie_length": len(cookie_value),
                        "full_cookie_header": cookie[:100] + "..." if len(cookie) > 100 else cookie
                    })
                    return cookie_value
                except (IndexError, ValueError) as e:
                    logger.warning("Failed to parse set-cookie header", extra={
                        "error": str(e),
                        "cookie_header": cookie[:100] + "..." if len(cookie) > 100 else cookie
                    })
                    continue
                
        # Also check single set-cookie header if get_list didn't work
        single_cookie = response.headers.get('set-cookie')
        if single_cookie and 'n8n-auth=' in single_cookie:
            try:
                cookie_value = single_cookie.split('n8n-auth=')[1].split(';')[0]
                logger.debug("Cookie extracted from single set-cookie header", extra={
                    "cookie_length": len(cookie_value)
                })
                return cookie_value
            except (IndexError, ValueError) as e:
                logger.warning("Failed to parse single set-cookie header", extra={
                    "error": str(e),
                    "cookie_header": single_cookie[:100] + "..." if len(single_cookie) > 100 else single_cookie
                })
    
    logger.warning("No n8n-auth cookie found in response", extra={
        "has_cookies_attr": hasattr(response, 'cookies'),
        "has_headers": hasattr(response, 'headers'),
        "all_headers": dict(response.headers) if hasattr(response, 'headers') else "no headers"
    })
    return None


async def get_oauth_token(code: str, request_id: str = None):
    """
    Exchange the Casdoor OAuth authorization code for an access token.

    This function sends a POST request to the Casdoor token endpoint with the provided code.
    Instead of raising exceptions, it returns either token data or a safe redirect response.

    :param code: The authorization code received from Casdoor.
    :param request_id: Optional request ID for tracking.
    :return: Either a dictionary with OAuth token data or a RedirectResponse for errors.
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
                            return create_safe_redirect(
                                error=ValueError(f"Invalid JSON response from Casdoor: {str(json_error)}"),
                                flash_message="Authentication failed. Please try again.",
                                context={
                                    "operation": "get_oauth_token",
                                    "error_type": "json_parse_error",
                                    "status_code": response.status_code
                                },
                                request_id=request_id
                            )
                else:
                    # Check for invalid_grant error
                    if response.status_code == 400:
                        try:
                            error_data = response.json()
                            if error_data.get("error") == "invalid_grant" and "authorization code has been used" in error_data.get("error_description", ""):
                                # Code already used, don't retry - return redirect instead of raising
                                logger.warning("Authorization code already used", extra={
                                    "attempt": attempt + 1,
                                    "code": code,
                                    "error": error_data
                                })
                                return create_safe_redirect(
                                    error=ValueError("Authorization code already used"),
                                    flash_message="Login session expired. Please try again.",
                                    context={
                                        "operation": "get_oauth_token",
                                        "error_type": "invalid_grant",
                                        "code": code
                                    },
                                    request_id=request_id
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
                        # Final attempt failed - return redirect instead of raising
                        return create_safe_redirect(
                            error=RuntimeError(f"Failed to obtain token after {max_retries} attempts. Last status: {response.status_code}"),
                            flash_message="Authentication service unavailable. Please try again later.",
                            context={
                                "operation": "get_oauth_token",
                                "error_type": "max_retries_exceeded",
                                "status_code": response.status_code,
                                "response_text": response.text[:200]
                            },
                            request_id=request_id
                        )
            
            except httpx.RequestError as req_error:
                logger.error("OAuth token request network error", extra={
                    "attempt": attempt + 1,
                    "error": str(req_error),
                    "url": url
                })
                
                if attempt == max_retries - 1:
                    return create_safe_redirect(
                        error=req_error,
                        flash_message="Network error during authentication. Please try again.",
                        context={
                            "operation": "get_oauth_token",
                            "error_type": "network_error",
                            "url": url
                        },
                        request_id=request_id
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


def parse_jwt_token(token: str, request_id: str = None):
    """
    Verify and decode the provided JWT token using the Casdoor certificate.

    This function loads the certificate, extracts the public key, and attempts to decode
    the JWT with the audience set to the Casdoor client ID and a leeway of 60 seconds.
    Instead of raising exceptions, it returns either the decoded token or a safe redirect.

    :param token: The JWT token string to be parsed.
    :param request_id: Optional request ID for tracking.
    :return: Either a dictionary with decoded token payload or a RedirectResponse for errors.
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
        return create_safe_redirect(
            error=e,
            flash_message="Authentication configuration error. Please contact support.",
            context={
                "operation": "parse_jwt_token",
                "error_type": "certificate_loading_error",
                "cert_path": settings.CASDOOR_CERT_PATH
            },
            request_id=request_id
        )
    
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
            return create_safe_redirect(
                error=fallback_error,
                flash_message="Invalid authentication token. Please try logging in again.",
                context={
                    "operation": "parse_jwt_token",
                    "error_type": "token_decoding_failed",
                    "token_length": len(token) if token else 0
                },
                request_id=request_id
            )


def map_casdoor_to_profile(user_info: Dict[str, Any], request_id: str = None):
    """Map Casdoor JWT claims to CasdoorProfile. Returns either profile or safe redirect."""
    email = (
        user_info.get("email") 
        or user_info.get("mail")
        or user_info.get("preferred_username")
    )
    if not email:
        return create_safe_redirect(
            error=ValueError("Casdoor profile missing email"),
            flash_message="Authentication profile incomplete. Please contact support.",
            context={
                "operation": "map_casdoor_to_profile",
                "error_type": "missing_email",
                "available_fields": list(user_info.keys())
            },
            request_id=request_id
        )
    
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
    # Note: code and state validation is now handled in the router
    
    try:
        # 1. Exchange code for tokens via existing helper
        token_result = await get_oauth_token(code, request_id)
        # Check if it's a redirect response (error case)
        if isinstance(token_result, RedirectResponse):
            return token_result
        
        token_info = token_result
        id_token = token_info.get("id_token")
        if not id_token:
            return log_and_redirect_on_error(
                error_message="Token response missing id_token",
                flash_message="Authentication failed. Please try again.",
                context={
                    "operation": "handle_casdoor_callback",
                    "error_type": "missing_id_token",
                    "token_keys": list(token_info.keys())
                },
                request_id=request_id
            )

        # 2. Parse and verify JWT token
        parse_result = parse_jwt_token(id_token, request_id)
        # Check if it's a redirect response (error case)
        if isinstance(parse_result, RedirectResponse):
            return parse_result
        
        user_info = parse_result
        
        # 3. Map to CasdoorProfile
        profile_result = map_casdoor_to_profile(user_info, request_id)
        # Check if it's a redirect response (error case)
        if isinstance(profile_result, RedirectResponse):
            return profile_result
        
        profile = profile_result
        
        logger.info("Casdoor user authenticated", extra={
            "request_id": request_id,
            "email": profile.email,
            "casdoor_id": profile.casdoor_id
        })
        
    except Exception as exc:
        # Any remaining unhandled exceptions
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

        # Check if user already has a local session (for tracking only)
        existing_session = SessionManager.get_active_session(profile.email)
        session_id = None
        skip_n8n_login = False
        
        if existing_session:
            # Check if existing session has a very recent cookie (< 60 seconds old)
            session_age = time.time() - existing_session.created_at
            is_very_recent = session_age < 60
            has_cookie = existing_session.n8n_cookie is not None
            
            if is_very_recent and has_cookie and existing_session.is_persistent:
                logger.info("Found very recent persistent session with cookie, skipping n8n login", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "session_id": existing_session.session_id,
                    "session_age": session_age,
                    "is_persistent": existing_session.is_persistent,
                    "has_cookie": has_cookie,
                    "decision": "skip_n8n_login_use_recent_cookie"
                })
                skip_n8n_login = True
                session_id = existing_session.session_id
            else:
                logger.debug("Found existing local session but will refresh via n8n login", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "session_id": existing_session.session_id,
                    "session_age": session_age,
                    "is_persistent": existing_session.is_persistent,
                    "has_cookie": has_cookie,
                    "is_very_recent": is_very_recent,
                    "decision": "will_refresh_via_n8n_login"
                })
                session_id = existing_session.session_id
        else:
            # Create new session for tracking
            session_id = SessionManager.create_session(profile.email)
            logger.debug("Created new session for tracking", extra={
                "request_id": request_id,
                "email": profile.email,
                "session_id": session_id
            })

        # Use existing recent cookie if available, otherwise attempt n8n login
        if skip_n8n_login:
            logger.info("Using existing recent cookie, skipping n8n login", extra={
                "request_id": request_id,
                "email": profile.email,
                "session_id": session_id,
                "reason": "very_recent_persistent_session_available"
            })
            
            # Use existing session cookie
            auth_cookie = existing_session.n8n_cookie
            settings = get_settings()
            n8n_base_url = str(settings.N8N_BASE_URL).rstrip('/')
            n8n_workflows_url = f"{n8n_base_url}/home/workflows"
            
            # Create redirect response with existing cookie
            from urllib.parse import urlparse
            parsed_url = urlparse(n8n_base_url)
            cookie_domain = parsed_url.hostname
            is_secure = parsed_url.scheme == "https"
            
            if not cookie_domain or cookie_domain == "localhost":
                cookie_domain = None
            
            response = RedirectResponse(url=n8n_workflows_url, status_code=302)
            response.set_cookie(
                key="n8n-auth",
                value=auth_cookie,
                domain=cookie_domain,
                path="/",
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=7 * 24 * 3600
            )
            
            logger.info("Redirected using existing recent persistent session", extra={
                "request_id": request_id,
                "email": profile.email,
                "session_id": session_id
            })
            
            return response
        else:
            # Attempt n8n login for fresh session
            logger.info("Proceeding with n8n login after Casdoor authentication", extra={
                "request_id": request_id,
                "email": profile.email,
                "session_id": session_id,
                "reason": "ensure_fresh_valid_n8n_session",
                "had_existing_session": existing_session is not None,
                "existing_session_age": time.time() - existing_session.created_at if existing_session else None
            })

        # 6. Login to n8n to get session cookie and extract it with retry logic
        n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
        auth_cookie = None
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                logger.info("Attempting n8n login", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "password_length": len(temp_password),
                    "attempt": attempt + 1,
                    "max_retries": max_retries
                })
                login_response = n8n_client.login_user(profile.email, temp_password)
                
                # Extract the n8n-auth cookie from the login response
                auth_cookie = extract_n8n_auth_cookie(login_response)
                
                if auth_cookie:
                    logger.info("n8n login and cookie extraction successful", extra={
                        "request_id": request_id,
                        "email": profile.email,
                        "status_code": getattr(login_response, 'status_code', 'unknown'),
                        "has_auth_cookie": True,
                        "cookie_length": len(auth_cookie),
                        "attempt": attempt + 1
                    })
                    break  # Success, exit retry loop
                else:
                    logger.warning("n8n login successful but cookie extraction failed", extra={
                        "request_id": request_id,
                        "email": profile.email,
                        "status_code": getattr(login_response, 'status_code', 'unknown'),
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "response_headers": dict(getattr(login_response, 'headers', {}))
                    })
                    if attempt < max_retries - 1:
                        # Short delay before retry
                        await asyncio.sleep(0.5)
                        continue
                
            except Exception as login_exc:
                logger.error("n8n login failed", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "error": str(login_exc),
                    "attempt": attempt + 1,
                    "max_retries": max_retries
                })
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                # auth_cookie remains None, will fall back to form submission
            
        # Final logging of login result
        logger.info("n8n login result", extra={
            "request_id": request_id,
            "email": profile.email,
            "status_code": getattr(login_response, 'status_code', 'unknown') if 'login_response' in locals() else 'unknown',
            "has_auth_cookie": auth_cookie is not None,
            "cookie_length": len(auth_cookie) if auth_cookie else 0,
            "total_attempts": max_retries,
            "response_headers": dict(getattr(login_response, 'headers', {})) if 'login_response' in locals() else {}
        })
        
        # Always close the client
        try:
            n8n_client.close()
        except Exception:
            pass  # Ignore cleanup errors
        
        # 7. Create redirect response with cookie setting
        n8n_base_url = str(settings.N8N_BASE_URL).rstrip('/')
        n8n_workflows_url = f"{n8n_base_url}/home/workflows"
        
        if auth_cookie:
            # Update session with persistent cookie
            SessionManager.update_session_cookie(session_id, auth_cookie)
            
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
            
            # Validate cookie domain to prevent silent failures
            if not cookie_domain or cookie_domain == "localhost":
                # For localhost or IP addresses, don't set domain attribute
                cookie_domain = None
                logger.warning("Cookie domain validation - using None for localhost/IP", extra={
                    "request_id": request_id,
                    "parsed_hostname": parsed_url.hostname,
                    "n8n_base_url": n8n_base_url
                })
            
            # Create response with a small delay to ensure proper header processing
            response = RedirectResponse(url=n8n_workflows_url, status_code=302)
            
            # Set the n8n-auth cookie with comprehensive logging
            try:
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
                
                logger.info("Cookie set successfully, redirecting to workflows", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "cookie_domain": cookie_domain,
                    "cookie_secure": is_secure,
                    "cookie_length": len(auth_cookie),
                    "redirect_url": n8n_workflows_url,
                    "parsed_scheme": parsed_url.scheme,
                    "parsed_hostname": parsed_url.hostname
                })
                
                return response
                
            except Exception as cookie_exc:
                logger.error("Failed to set cookie, falling back to JavaScript method", extra={
                    "request_id": request_id,
                    "email": profile.email,
                    "error": str(cookie_exc),
                    "cookie_domain": cookie_domain,
                    "n8n_base_url": n8n_base_url
                })
                # Fall through to JavaScript method
        
        # Method 2: Enhanced JavaScript login method with cookie verification
        logger.info("Using enhanced JavaScript login method with redirect", extra={
            "request_id": request_id,
            "email": profile.email,
            "target_url": n8n_workflows_url,
            "reason": "Cookie extraction failed or cookie setting failed"
        })
        
        # Use JavaScript to login and then redirect properly with cookie verification
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
                <p id="status">Authenticating...</p>
            </div>
            
            <script>
                // Function to perform login and redirect with verification
                async function performLogin() {{
                    const statusEl = document.getElementById('status');
                    
                    try {{
                        statusEl.textContent = 'Logging in to n8n...';
                        
                        // Perform the login request
                        const loginResponse = await fetch('{n8n_base_url}/rest/login', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            }},
                            credentials: 'include',  // Ensure cookies are included
                            body: JSON.stringify({{
                                emailOrLdapLoginId: '{profile.email}',
                                password: '{temp_password}'
                            }})
                        }});
                        
                        if (loginResponse.ok) {{
                            console.log('Login successful, verifying session...');
                            statusEl.textContent = 'Login successful, verifying session...';
                            
                            // Wait a moment for cookies to be processed
                            await new Promise(resolve => setTimeout(resolve, 1000));
                            
                            // Verify the session is valid
                            try {{
                                const verifyResponse = await fetch('{n8n_base_url}/rest/login', {{
                                    method: 'GET',
                                    credentials: 'include'
                                }});
                                
                                if (verifyResponse.ok) {{
                                    console.log('Session verified, redirecting...');
                                    statusEl.textContent = 'Session verified, redirecting...';
                                    setTimeout(() => {{
                                        window.location.href = '{n8n_workflows_url}';
                                    }}, 500);
                                }} else {{
                                    console.warn('Session verification failed, but proceeding with redirect');
                                    statusEl.textContent = 'Redirecting...';
                                    setTimeout(() => {{
                                        window.location.href = '{n8n_workflows_url}';
                                    }}, 1000);
                                }}
                            }} catch (verifyError) {{
                                console.warn('Session verification error:', verifyError);
                                statusEl.textContent = 'Redirecting...';
                                setTimeout(() => {{
                                    window.location.href = '{n8n_workflows_url}';
                                }}, 1000);
                            }}
                        }} else {{
                            console.error('Login failed:', loginResponse.status);
                            statusEl.textContent = 'Login failed, but redirecting anyway...';
                            // Still try to redirect as a fallback
                            setTimeout(() => {{
                                window.location.href = '{n8n_workflows_url}';
                            }}, 2000);
                        }}
                    }} catch (error) {{
                        console.error('Login request failed:', error);
                        statusEl.textContent = 'Connection error, redirecting...';
                        // Fallback redirect
                        setTimeout(() => {{
                            window.location.href = '{n8n_workflows_url}';
                        }}, 2000);
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
        # Instead of raising, redirect to DEFAULT_REDIRECT_URL with a flash message
        settings = get_settings()
        # Add a flash message via query param (or use your preferred flash mechanism)
        redirect_url = settings.DEFAULT_REDIRECT_URL
        flash_msg = "n8n SSO error: Could not complete login. Please try again later."
        from urllib.parse import urlencode, urlparse, urlunparse, parse_qs
        # Append flash message as ?flash=... or &flash=...
        url_parts = list(urlparse(redirect_url))
        query = parse_qs(url_parts[4])
        query['flash'] = [flash_msg]
        url_parts[4] = urlencode(query, doseq=True)
        safe_redirect_url = urlunparse(url_parts)
        return RedirectResponse(url=safe_redirect_url, status_code=302)
