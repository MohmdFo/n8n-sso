"""
Prometheus Metrics Middleware for FastAPI

This middleware automatically collects metrics for all HTTP requests including:
- Request timing
- Status codes
- Error tracking
- Performance monitoring

The middleware integrates seamlessly with FastAPI and provides comprehensive
request-level metrics collection without requiring manual instrumentation.
"""

import time
import logging
from typing import Callable, Dict, Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .base import (
    record_request_metrics,
    record_error,
    REQUEST_COUNTER,
    REQUEST_DURATION
)

logger = logging.getLogger(__name__)

class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic Prometheus metrics collection.
    
    This middleware automatically tracks:
    - HTTP request counts and durations
    - Status code distribution
    - Error rates and types
    - API version usage
    """
    
    def __init__(self, app: ASGIApp, app_name: str = "n8n-sso-gateway"):
        """
        Initialize the metrics middleware.
        
        Args:
            app: The ASGI application
            app_name: Name of the application for metrics labeling
        """
        super().__init__(app)
        self.app_name = app_name
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and collect metrics.
        
        Args:
            request: The incoming HTTP request
            call_next: Function to call the next middleware/endpoint
            
        Returns:
            Response: The HTTP response
        """
        start_time = time.time()
        
        # Extract request information
        method = request.method
        endpoint = self._get_endpoint_path(request)
        version = self._extract_api_version(request)
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate request duration
            duration = time.time() - start_time
            
            # Record successful request metrics
            record_request_metrics(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration,
                version=version
            )
            
            # Log request completion
            logger.debug(
                f"Request completed: {method} {endpoint} - {response.status_code} "
                f"({duration:.4f}s)"
            )
            
            return response
            
        except Exception as exc:
            # Calculate duration even for failed requests
            duration = time.time() - start_time
            
            # Record error metrics
            error_type = self._classify_error(exc)
            record_error(
                error_type=error_type,
                endpoint=endpoint,
                severity=self._assess_error_severity(exc)
            )
            
            # Record failed request metrics (status 500)
            record_request_metrics(
                method=method,
                endpoint=endpoint,
                status_code=500,
                duration=duration,
                version=version
            )
            
            # Log the error
            logger.error(
                f"Request failed: {method} {endpoint} - Error: {error_type} "
                f"({duration:.4f}s) - {str(exc)}",
                exc_info=True
            )
            
            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": "An unexpected error occurred",
                    "error_type": error_type
                }
            )
    
    def _get_endpoint_path(self, request: Request) -> str:
        """
        Extract the endpoint path for metrics labeling.
        
        Args:
            request: The HTTP request
            
        Returns:
            str: Normalized endpoint path
        """
        path = request.url.path
        
        # Normalize path for metrics (remove version prefix if present)
        if path.startswith('/v'):
            # Remove version prefix for consistent metrics
            path = path[path.find('/', 1):] if path.count('/') > 1 else '/'
        
        # Handle root path
        if not path or path == '/':
            path = '/'
        
        # Limit path length to prevent cardinality issues
        if len(path) > 100:
            path = path[:100] + '...'
        
        return path
    
    def _extract_api_version(self, request: Request) -> str:
        """
        Extract API version from the request path.
        
        Args:
            request: The HTTP request
            
        Returns:
            str: API version (default: v1)
        """
        path = request.url.path
        
        # Extract version from path like /v1/auth/login
        if path.startswith('/v') and len(path) > 2:
            version_part = path[1:3]  # Extract 'v1', 'v2', etc.
            if version_part[1].isdigit():
                return version_part
        
        return "v1"  # Default version
    
    def _classify_error(self, exc: Exception) -> str:
        """
        Classify the type of error for metrics labeling.
        
        Args:
            exc: The exception that occurred
            
        Returns:
            str: Error type classification
        """
        error_type = type(exc).__name__
        
        # Map common exception types to standardized categories
        error_mapping = {
            'ValidationError': 'validation',
            'AuthenticationError': 'authentication',
            'AuthorizationError': 'authorization',
            'DatabaseError': 'database',
            'ConnectionError': 'connection',
            'TimeoutError': 'timeout',
            'ValueError': 'validation',
            'TypeError': 'validation',
            'KeyError': 'validation',
            'AttributeError': 'validation',
            'FileNotFoundError': 'file_not_found',
            'PermissionError': 'permission',
            'OSError': 'system',
            'MemoryError': 'system',
            'RecursionError': 'system'
        }
        
        return error_mapping.get(error_type, 'unknown')
    
    def _assess_error_severity(self, exc: Exception) -> str:
        """
        Assess the severity of an error for metrics labeling.
        
        Args:
            exc: The exception that occurred
            
        Returns:
            str: Error severity (low, medium, high, critical)
        """
        # Critical errors that indicate system failure
        critical_errors = {
            'MemoryError',
            'RecursionError',
            'SystemError',
            'KeyboardInterrupt'
        }
        
        # High severity errors that affect functionality
        high_severity_errors = {
            'DatabaseError',
            'ConnectionError',
            'TimeoutError',
            'OSError'
        }
        
        # Medium severity errors that affect user experience
        medium_severity_errors = {
            'ValidationError',
            'AuthenticationError',
            'AuthorizationError',
            'PermissionError'
        }
        
        error_type = type(exc).__name__
        
        if error_type in critical_errors:
            return 'critical'
        elif error_type in high_severity_errors:
            return 'high'
        elif error_type in medium_severity_errors:
            return 'medium'
        else:
            return 'low'

class MetricsContextMiddleware(BaseHTTPMiddleware):
    """
    Additional middleware for context-aware metrics collection.
    
    This middleware provides additional context for metrics collection
    such as user identification, request correlation, and custom labels.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add metrics context to the request.
        
        Args:
            request: The HTTP request
            call_next: Function to call the next middleware/endpoint
            
        Returns:
            Response: The HTTP response
        """
        # Add metrics context to request state
        request.state.metrics_context = {
            'start_time': time.time(),
            'user_id': self._extract_user_id(request),
            'correlation_id': self._extract_correlation_id(request),
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent', 'unknown')
        }
        
        response = await call_next(request)
        
        # Add metrics headers to response
        if hasattr(request.state, 'metrics_context'):
            response.headers['X-Request-ID'] = request.state.metrics_context['correlation_id']
        
        return response
    
    def _extract_user_id(self, request: Request) -> str:
        """
        Extract user ID from request headers or JWT token.
        
        Args:
            request: The HTTP request
            
        Returns:
            str: User ID or 'anonymous'
        """
        # Check for user ID in headers
        user_id = request.headers.get('X-User-ID')
        if user_id:
            return user_id
        
        # Check for authorization header
        auth_header = request.headers.get('authorization')
        if auth_header and auth_header.startswith('Bearer '):
            # In a real implementation, you would decode the JWT here
            # For now, return a placeholder
            return 'authenticated'
        
        return 'anonymous'
    
    def _extract_correlation_id(self, request: Request) -> str:
        """
        Extract or generate correlation ID for request tracking.
        
        Args:
            request: The HTTP request
            
        Returns:
            str: Correlation ID
        """
        # Check for existing correlation ID
        correlation_id = request.headers.get('X-Correlation-ID')
        if correlation_id:
            return correlation_id
        
        # Generate new correlation ID
        import uuid
        return str(uuid.uuid4())
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Get the client IP address from request headers.
        
        Args:
            request: The HTTP request
            
        Returns:
            str: Client IP address
        """
        # Check for forwarded headers (common in proxy setups)
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        # Fall back to client host
        return str(request.client.host) if request.client else 'unknown'
