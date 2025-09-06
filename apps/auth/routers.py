from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from .services import handle_casdoor_callback
from .casdoor_utils import get_casdoor_login_url
from .webhook_services import handle_casdoor_logout_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/casdoor", tags=["Casdoor Auth"])


@router.get("/callback", summary="Casdoor OAuth callback")
async def casdoor_callback(request: Request):
    """Handle Casdoor OAuth callback and redirect to n8n."""
    try:
        return await handle_casdoor_callback(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in Casdoor callback")
        raise HTTPException(status_code=500, detail="Internal error") from exc


@router.get("/login", summary="Start Casdoor login and redirect to n8n")
async def casdoor_login(request: Request):
    """Initiate Casdoor login flow."""
    try:
        # Build callback URL for this FastAPI app
        callback_url = str(request.url_for("casdoor_callback"))
        login_url = get_casdoor_login_url(callback_url)
        return RedirectResponse(url=login_url, status_code=302)
    except Exception as exc:
        logger.exception("Failed to generate Casdoor login URL")
        raise HTTPException(status_code=500, detail="Login service unavailable") from exc


@router.post("/webhook", summary="Casdoor webhook for logout synchronization")
async def casdoor_webhook(request: Request):
    """Handle Casdoor webhook events (especially logout events)."""
    try:
        payload = await request.json()
        
        logger.info("Received Casdoor webhook", extra={
            "action": payload.get("action"),
            "user": payload.get("user"),
            "organization": payload.get("organization")
        })
        
        # Handle the webhook
        result = await handle_casdoor_logout_webhook(payload)
        
        return {
            "success": True,
            "webhook_id": payload.get("id"),
            "result": result
        }
        
    except Exception as exc:
        logger.exception("Webhook processing failed")
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc


@router.get("/logout", summary="Manual logout from n8n")
async def casdoor_logout(request: Request):
    """Manual logout endpoint - logs user out of n8n and redirects to Casdoor."""
    try:
        from apps.integrations.n8n_client import N8NClient
        from conf.settings import get_settings
        
        settings = get_settings()
        
        # Get auth cookie from request if present
        auth_cookie = request.cookies.get("n8n-auth")
        
        # Logout from n8n
        n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
        try:
            logout_response = n8n_client.logout_user(auth_cookie)
            logger.info("Manual n8n logout completed", extra={
                "status_code": logout_response.status_code,
                "had_auth_cookie": auth_cookie is not None
            })
        except Exception as logout_exc:
            logger.error("Manual n8n logout failed", extra={"error": str(logout_exc)})
        finally:
            n8n_client.close()
        
        # Redirect to Casdoor logout
        casdoor_logout_url = f"{str(settings.CASDOOR_ENDPOINT).rstrip('/')}/logout"
        
        # Create redirect response that also clears cookies
        response = RedirectResponse(url=casdoor_logout_url, status_code=302)
        
        # Clear the n8n-auth cookie
        response.delete_cookie(key="n8n-auth", path="/")
        
        return response
        
    except Exception as exc:
        logger.exception("Manual logout failed")
        raise HTTPException(status_code=500, detail="Logout failed") from exc
