"""Casdoor webhook handlers for logout synchronization."""
from __future__ import annotations

import logging
import json
from typing import Dict, Any
from fastapi import HTTPException

from apps.integrations.n8n_client import N8NClient
from apps.integrations.n8n_db import get_user_by_email
from conf.settings import get_settings

logger = logging.getLogger(__name__)

class CasdoorWebhookPayload:
    """Represents a Casdoor webhook payload."""
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.owner = data.get("owner")
        self.name = data.get("name")
        self.created_time = data.get("createdTime")
        self.organization = data.get("organization")
        self.client_ip = data.get("clientIp")
        self.user = data.get("user")
        self.method = data.get("method")
        self.request_uri = data.get("requestUri")
        self.action = data.get("action")
        self.is_triggered = data.get("isTriggered")
        self.object = data.get("object")
        self.extended_user = data.get("extendedUser", {})
        
        # Also try to get user info from the main payload if extendedUser is empty
        if not self.extended_user and data.get("object"):
            # Sometimes the user info is in the "object" field
            obj = data["object"]
            if isinstance(obj, dict) and obj.get("email"):
                self.extended_user = {
                    "email": obj.get("email"),
                    "name": obj.get("name"),
                    "displayName": obj.get("displayName") or obj.get("firstName", "") + " " + obj.get("lastName", "").strip()
                }
        
    @property
    def user_email(self) -> str | None:
        """Get user email from extended user data."""
        return self.extended_user.get("email")
    
    @property 
    def user_name(self) -> str | None:
        """Get user name from extended user data."""
        return self.extended_user.get("name")
    
    @property
    def display_name(self) -> str | None:
        """Get display name from extended user data."""
        return self.extended_user.get("displayName")
    
    def is_logout_event(self) -> bool:
        """Check if this is a logout event."""
        return self.action == "logout"

async def handle_casdoor_logout_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Casdoor logout webhook.
    
    When a user logs out from Casdoor, this function:
    1. Parses the webhook payload
    2. Identifies the user
    3. Logs them out from n8n
    4. Returns success/failure status
    """
    webhook_data = CasdoorWebhookPayload(payload)
    request_id = str(webhook_data.id)[:8] if webhook_data.id else "unknown"
    
    # Debug: Log the full payload to understand what we're receiving
    logger.info("Received Casdoor webhook", extra={
        "request_id": request_id,
        "action": webhook_data.action,
        "user": webhook_data.user_name,
        "email": webhook_data.user_email,
        "organization": webhook_data.organization,
        "full_payload": payload,  # Add full payload for debugging
        "extended_user": webhook_data.extended_user
    })
    
    # Only handle logout events
    if not webhook_data.is_logout_event():
        logger.info("Ignoring non-logout webhook event", extra={
            "request_id": request_id,
            "action": webhook_data.action
        })
        return {"status": "ignored", "reason": "not_logout_event"}
    
    user_email = webhook_data.user_email
    if not user_email:
        logger.warning("Logout webhook missing user email", extra={
            "request_id": request_id,
            "user": webhook_data.user_name
        })
        return {"status": "error", "reason": "missing_user_email"}
    
    try:
        settings = get_settings()
        
        # Try to find the user in n8n database to get their current session info
        user_row = None
        try:
            user_row = await get_user_by_email(user_email)
            logger.info("Found n8n user for logout", extra={
                "request_id": request_id,
                "email": user_email,
                "user_id": str(user_row.id) if user_row else "not_found"
            })
        except Exception as db_exc:
            logger.warning("Could not find user in n8n database", extra={
                "request_id": request_id,
                "email": user_email,
                "error": str(db_exc)
            })
        
        # Attempt to logout from n8n
        n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
        
        try:
            # Method 1: Try API-based logout (login as user, then logout)
            logout_response = n8n_client.logout_user_by_email(user_email)
            
            if logout_response.status_code < 400:
                logger.info("n8n logout API successful via webhook", extra={
                    "request_id": request_id,
                    "email": user_email,
                    "status_code": logout_response.status_code,
                    "approach": "api_login_logout"
                })
                
                return {
                    "status": "success",
                    "user_email": user_email,
                    "n8n_logout_status": logout_response.status_code,
                    "method": "api_logout",
                    "message": "User logged out from n8n via API"
                }
            else:
                # Method 2: Fallback to database approach (password rotation)
                logger.warning("API logout failed, trying database approach", extra={
                    "request_id": request_id,
                    "email": user_email,
                    "api_status": logout_response.status_code
                })
                
                from apps.integrations.n8n_db import invalidate_user_sessions_db
                db_success = await invalidate_user_sessions_db(user_email)
                
                if db_success:
                    return {
                        "status": "success",
                        "user_email": user_email,
                        "method": "database_invalidation",
                        "message": "User sessions invalidated via database (password rotation)"
                    }
                else:
                    return {
                        "status": "partial_failure",
                        "user_email": user_email,
                        "api_status": logout_response.status_code,
                        "db_status": "failed",
                        "message": "Both API and database logout methods failed"
                    }
            
        except Exception as logout_exc:
            logger.error("Failed to logout user from n8n", extra={
                "request_id": request_id,
                "email": user_email,
                "error": str(logout_exc)
            })
            
            return {
                "status": "error",
                "user_email": user_email,
                "error": str(logout_exc),
                "message": "Failed to logout from n8n"
            }
        
        finally:
            n8n_client.close()
            
    except Exception as exc:
        logger.exception("Webhook processing failed", extra={
            "request_id": request_id,
            "email": user_email,
            "error": str(exc)
        })
        raise HTTPException(
            status_code=500, 
            detail=f"Webhook processing failed: {str(exc)}"
        )
