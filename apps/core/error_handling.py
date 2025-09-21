"""
Centralized error handling utilities for graceful error handling and user redirection.

This module provides utilities to log critical errors and safely redirect users
to DEFAULT_REDIRECT_URL instead of crashing the service with unhandled exceptions.
"""
from __future__ import annotations

import uuid
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from fastapi.responses import RedirectResponse
from fastapi import HTTPException

from conf.settings import get_settings
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)


def create_safe_redirect(
    error: Exception,
    flash_message: Optional[str] = None,
    context: Optional[dict] = None,
    request_id: Optional[str] = None
) -> RedirectResponse:
    """
    Create a safe redirect response with error logging instead of raising exceptions.
    
    This function logs the error as critical and creates a redirect to DEFAULT_REDIRECT_URL
    with an optional flash message, ensuring the service remains available to users.
    
    Args:
        error: The exception that occurred
        flash_message: Optional flash message to show to the user
        context: Optional context dictionary for logging
        request_id: Optional request ID for tracking
        
    Returns:
        RedirectResponse to DEFAULT_REDIRECT_URL with optional flash message
    """
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
    
    settings = get_settings()
    
    # Log the error as critical with full context
    log_context = {
        "request_id": request_id,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "redirect_url": settings.DEFAULT_REDIRECT_URL,
        "flash_message": flash_message,
    }
    
    if context:
        log_context.update(context)
    
    logger.critical("Critical error handled gracefully with redirect", extra=log_context, exc_info=error)
    
    # Create redirect URL with flash message if provided
    redirect_url = settings.DEFAULT_REDIRECT_URL
    
    if flash_message:
        url_parts = list(urlparse(redirect_url))
        query = parse_qs(url_parts[4])
        query['flash'] = [flash_message]
        url_parts[4] = urlencode(query, doseq=True)
        redirect_url = urlunparse(url_parts)
    
    return RedirectResponse(url=redirect_url, status_code=302)


def log_and_redirect_on_error(
    error_message: str,
    flash_message: Optional[str] = None,
    context: Optional[dict] = None,
    request_id: Optional[str] = None
) -> RedirectResponse:
    """
    Log an error message as critical and create a safe redirect.
    
    This is a simplified version for cases where you want to log a message
    without having an actual exception object.
    
    Args:
        error_message: The error message to log
        flash_message: Optional flash message to show to the user
        context: Optional context dictionary for logging
        request_id: Optional request ID for tracking
        
    Returns:
        RedirectResponse to DEFAULT_REDIRECT_URL with optional flash message
    """
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
    
    settings = get_settings()
    
    # Log the error as critical
    log_context = {
        "request_id": request_id,
        "error_message": error_message,
        "redirect_url": settings.DEFAULT_REDIRECT_URL,
        "flash_message": flash_message,
    }
    
    if context:
        log_context.update(context)
    
    logger.critical("Critical error logged with safe redirect", extra=log_context)
    
    # Create redirect URL with flash message if provided
    redirect_url = settings.DEFAULT_REDIRECT_URL
    
    if flash_message:
        url_parts = list(urlparse(redirect_url))
        query = parse_qs(url_parts[4])
        query['flash'] = [flash_message]
        url_parts[4] = urlencode(query, doseq=True)
        redirect_url = urlunparse(url_parts)
    
    return RedirectResponse(url=redirect_url, status_code=302)


class SafeRedirectHandler:
    """
    Context manager for safe error handling that redirects instead of raising.
    
    Usage:
        with SafeRedirectHandler(request_id="abc123", flash_message="Error occurred") as handler:
            # Code that might raise exceptions
            result = some_operation()
            return result
        # If an exception occurs, it returns a RedirectResponse automatically
    """
    
    def __init__(
        self, 
        request_id: Optional[str] = None,
        flash_message: Optional[str] = None,
        context: Optional[dict] = None
    ):
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.flash_message = flash_message
        self.context = context or {}
        self.result = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            # An exception occurred, return a safe redirect
            self.result = create_safe_redirect(
                error=exc_value,
                flash_message=self.flash_message,
                context=self.context,
                request_id=self.request_id
            )
            # Suppress the exception by returning True
            return True
        return False
    
    def get_result(self):
        """Get the result (either success result or redirect response)."""
        return self.result


def safe_operation(
    operation_name: str,
    default_flash_message: str = "An error occurred. Please try again later."
):
    """
    Decorator for safely executing operations with automatic error handling.
    
    Args:
        operation_name: Name of the operation for logging
        default_flash_message: Default message to show users on error
        
    Usage:
        @safe_operation("user_login", "Login failed. Please try again.")
        async def login_user(email: str, password: str):
            # Code that might raise exceptions
            return result
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                return create_safe_redirect(
                    error=exc,
                    flash_message=default_flash_message,
                    context={
                        "operation": operation_name,
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys())
                    },
                    request_id=request_id
                )
        
        def sync_wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                return create_safe_redirect(
                    error=exc,
                    flash_message=default_flash_message,
                    context={
                        "operation": operation_name,
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys())
                    },
                    request_id=request_id
                )
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def safe_api_operation(
    operation_name: str,
    default_status_code: int = 500,
    default_detail: str = "Internal server error"
):
    """
    Decorator for safely executing API operations that should return JSON errors.
    
    For webhook endpoints and APIs that need to return structured error responses
    instead of redirects.
    
    Args:
        operation_name: Name of the operation for logging
        default_status_code: HTTP status code to return on error
        default_detail: Error message to return
        
    Usage:
        @safe_api_operation("webhook_processing", 500, "Webhook processing failed")
        async def process_webhook(payload: dict):
            # Code that might raise exceptions
            return result
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                logger.critical("Critical error in API operation", extra={
                    "request_id": request_id,
                    "operation": operation_name,
                    "function": func.__name__,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                }, exc_info=exc)
                
                raise HTTPException(
                    status_code=default_status_code,
                    detail=f"{default_detail}: {str(exc)}"
                )
        
        def sync_wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                logger.critical("Critical error in API operation", extra={
                    "request_id": request_id,
                    "operation": operation_name,
                    "function": func.__name__,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                }, exc_info=exc)
                
                raise HTTPException(
                    status_code=default_status_code,
                    detail=f"{default_detail}: {str(exc)}"
                )
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
