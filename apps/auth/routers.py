from __future__ import annotations

import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from .services import handle_casdoor_callback
from .casdoor_utils import get_casdoor_login_url

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
