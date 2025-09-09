from __future__ import annotations

import logging
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from .services import handle_casdoor_callback
from .casdoor_utils import get_casdoor_login_url
from .webhook_services import handle_casdoor_logout_webhook
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/casdoor", tags=["Casdoor Auth"])


@router.get("/callback", summary="Casdoor OAuth callback")
async def casdoor_callback(request: Request):
    """Handle Casdoor OAuth callback and redirect to n8n."""
    request_id = str(uuid.uuid4())[:8]
    
    logger.info("OAuth callback received", extra={
        "request_id": request_id,
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "query_params": dict(request.query_params)
    })
    
    try:
        result = await handle_casdoor_callback(request)
        
        logger.info("OAuth callback completed successfully", extra={
            "request_id": request_id,
            "redirect_status": getattr(result, 'status_code', 'unknown')
        })
        
        return result
    except HTTPException as http_exc:
        logger.warning("OAuth callback HTTP error", extra={
            "request_id": request_id,
            "status_code": http_exc.status_code,
            "detail": http_exc.detail
        })
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in Casdoor callback", extra={
            "request_id": request_id,
            "error_type": type(exc).__name__
        })
        raise HTTPException(status_code=500, detail="Internal error") from exc


@router.get("/login", summary="Start Casdoor login and redirect to n8n")
async def casdoor_login(request: Request):
    """Initiate Casdoor login flow."""
    request_id = str(uuid.uuid4())[:8]
    
    logger.info("Login initiation requested", extra={
        "request_id": request_id,
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "referer": request.headers.get("referer", "unknown")
    })
    
    try:
        # Build callback URL for this FastAPI app
        callback_url = str(request.url_for("casdoor_callback"))
        login_url = get_casdoor_login_url(callback_url)
        
        logger.info("Redirecting to Casdoor login", extra={
            "request_id": request_id,
            "callback_url": callback_url,
            "login_url": login_url[:100] + "..." if len(login_url) > 100 else login_url
        })
        
        return RedirectResponse(url=login_url, status_code=302)
    except Exception as exc:
        logger.exception("Failed to generate Casdoor login URL", extra={
            "request_id": request_id,
            "error_type": type(exc).__name__
        })
        raise HTTPException(status_code=500, detail="Login service unavailable") from exc


@router.post("/webhook", summary="Casdoor webhook for logout synchronization")
async def casdoor_webhook(request: Request):
    """Handle Casdoor webhook events (especially logout events)."""
    webhook_id = str(uuid.uuid4())[:8]
    
    try:
        # Log webhook reception
        logger.info("Casdoor webhook received", extra={
            "webhook_id": webhook_id,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
            "content_type": request.headers.get("content-type", "unknown")
        })
        
        payload = await request.json()
        
        logger.info("Webhook payload parsed", extra={
            "webhook_id": webhook_id,
            "action": payload.get("action"),
            "user": payload.get("user"),
            "organization": payload.get("organization"),
            "webhook_event_id": payload.get("id"),
            "payload_keys": list(payload.keys()) if payload else []
        })
        
        # Handle the webhook
        result = await handle_casdoor_logout_webhook(payload)
        
        logger.info("Webhook processed successfully", extra={
            "webhook_id": webhook_id,
            "result_status": result.get("status") if isinstance(result, dict) else "unknown",
            "user_email": result.get("user_email") if isinstance(result, dict) else None
        })
        
        return {
            "success": True,
            "webhook_id": payload.get("id"),
            "processing_id": webhook_id,
            "result": result
        }
        
    except ValueError as json_exc:
        logger.error("Invalid JSON in webhook payload", extra={
            "webhook_id": webhook_id,
            "error": str(json_exc)
        })
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from json_exc
    except Exception as exc:
        logger.exception("Webhook processing failed", extra={
            "webhook_id": webhook_id,
            "error_type": type(exc).__name__
        })
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc


@router.get("/logout", summary="Manual logout from n8n")
async def casdoor_logout(request: Request):
    """Manual logout endpoint - logs user out of n8n and redirects to Casdoor."""
    logout_id = str(uuid.uuid4())[:8]
    
    logger.info("Manual logout requested", extra={
        "logout_id": logout_id,
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "referer": request.headers.get("referer", "unknown")
    })
    
    try:
        from apps.integrations.n8n_client import N8NClient
        from conf.settings import get_settings
        
        settings = get_settings()
        
        # Get auth cookie from request if present
        auth_cookie = request.cookies.get("n8n-auth")
        
        logger.info("Processing manual logout", extra={
            "logout_id": logout_id,
            "has_auth_cookie": auth_cookie is not None,
            "cookie_length": len(auth_cookie) if auth_cookie else 0
        })
        
        # Logout from n8n
        n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
        try:
            logout_response = n8n_client.logout_user(auth_cookie)
            logger.info("Manual n8n logout completed", extra={
                "logout_id": logout_id,
                "status_code": logout_response.status_code,
                "logout_successful": logout_response.status_code < 400,
                "response_text": logout_response.text[:100] if logout_response.text else "no response"
            })
        except Exception as logout_exc:
            logger.error("Manual n8n logout failed", extra={
                "logout_id": logout_id,
                "error": str(logout_exc),
                "error_type": type(logout_exc).__name__
            })
        finally:
            n8n_client.close()
        
        # Redirect to Casdoor logout
        casdoor_logout_url = f"{str(settings.CASDOOR_ENDPOINT).rstrip('/')}/logout"
        
        logger.info("Redirecting to Casdoor logout", extra={
            "logout_id": logout_id,
            "casdoor_logout_url": casdoor_logout_url
        })
        
        # Create redirect response that also clears cookies
        response = RedirectResponse(url=casdoor_logout_url, status_code=302)
        
        # Clear the n8n-auth cookie
        response.delete_cookie(key="n8n-auth", path="/")
        
        return response
        
    except Exception as exc:
        logger.exception("Manual logout failed", extra={
            "logout_id": logout_id,
            "error_type": type(exc).__name__
        })
        raise HTTPException(status_code=500, detail="Logout failed") from exc
