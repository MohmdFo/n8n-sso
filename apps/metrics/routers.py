"""
Prometheus Metrics Router for FastAPI

This module provides the /metrics endpoint that returns Prometheus-formatted metrics.
The endpoint is designed to be scraped by external Prometheus servers and includes
proper content type headers and error handling.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST

from .base import (
    generate_metrics_response,
    get_metrics_registry,
    update_service_health,
    SERVICE_HEALTH_GAUGE
)

logger = logging.getLogger(__name__)

# Create the metrics router
metrics_router = APIRouter(prefix="/metrics", tags=["Monitoring"])

@metrics_router.get(
    "/",
    summary="Get Prometheus Metrics",
    description="Returns Prometheus-formatted metrics for external scraping",
    response_class=PlainTextResponse,
    responses={
        200: {
            "description": "Prometheus metrics in text format",
            "content": {
                "text/plain": {
                    "example": "# HELP http_requests_total Total number of HTTP requests\n# TYPE http_requests_total counter\nhttp_requests_total{method=\"GET\",endpoint=\"/health\",status_code=\"200\",version=\"v1\"} 42"
                }
            }
        },
        500: {
            "description": "Internal server error while generating metrics"
        }
    }
)
async def get_metrics(request: Request) -> Response:
    """
    Get Prometheus metrics endpoint.
    
    This endpoint returns all application metrics in Prometheus exposition format.
    It's designed to be scraped by external Prometheus servers and includes
    comprehensive metrics about the application's performance and health.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Response: Plain text response with Prometheus metrics
        
    Raises:
        HTTPException: If there's an error generating metrics
    """
    try:
        # Log metrics request
        logger.debug(f"Metrics requested from {request.client.host if request.client else 'unknown'}")
        
        # Generate metrics response
        metrics_data, content_type = generate_metrics_response()
        
        # Update service health metric to indicate the endpoint is working
        update_service_health(
            service_name='n8n-sso-gateway',
            component='metrics_endpoint',
            is_healthy=True
        )
        
        # Return metrics with proper headers
        return Response(
            content=metrics_data,
            media_type=content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as exc:
        # Log the error
        logger.error(f"Error generating metrics: {str(exc)}", exc_info=True)
        
        # Update service health metric to indicate the endpoint is unhealthy
        update_service_health(
            service_name='n8n-sso-gateway',
            component='metrics_endpoint',
            is_healthy=False
        )
        
        # Return error response
        raise HTTPException(
            status_code=500,
            detail="Failed to generate metrics"
        )

@metrics_router.get(
    "/health",
    summary="Metrics Health Check",
    description="Check if the metrics system is healthy and accessible",
    responses={
        200: {
            "description": "Metrics system is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "metrics_count": 15,
                        "registry_size": "2.5KB"
                    }
                }
            }
        },
        500: {
            "description": "Metrics system is unhealthy"
        }
    }
)
async def metrics_health_check() -> Dict[str, Any]:
    """
    Health check endpoint for the metrics system.
    
    This endpoint provides information about the health and status
    of the Prometheus metrics collection system.
    
    Returns:
        Dict[str, Any]: Health status information
        
    Raises:
        HTTPException: If the metrics system is unhealthy
    """
    try:
        # Get metrics registry
        registry = get_metrics_registry()
        
        # Count metrics
        metrics_count = len(list(registry.collect()))
        
        # Estimate registry size (rough calculation)
        registry_size = len(str(registry.collect()))
        
        # Check if key metrics are available
        health_status = "healthy"
        
        # Verify that core metrics exist
        core_metrics = [
            'http_requests_total',
            'http_request_duration_seconds',
            'service_health_status'
        ]
        
        available_metrics = [metric.name for metric in registry.collect()]
        missing_metrics = [metric for metric in core_metrics if metric not in available_metrics]
        
        if missing_metrics:
            health_status = "degraded"
            logger.warning(f"Missing core metrics: {missing_metrics}")
        
        # Update service health metric
        update_service_health(
            service_name='n8n-sso-gateway',
            component='metrics_system',
            is_healthy=health_status == "healthy"
        )
        
        return {
            "status": health_status,
            "metrics_count": metrics_count,
            "registry_size": f"{registry_size} bytes",
            "core_metrics_available": len(core_metrics) - len(missing_metrics),
            "total_core_metrics": len(core_metrics),
            "missing_metrics": missing_metrics if missing_metrics else None
        }
        
    except Exception as exc:
        # Log the error
        logger.error(f"Metrics health check failed: {str(exc)}", exc_info=True)
        
        # Update service health metric
        update_service_health(
            service_name='n8n-sso-gateway',
            component='metrics_system',
            is_healthy=False
        )
        
        # Return error response
        raise HTTPException(
            status_code=500,
            detail=f"Metrics system health check failed: {str(exc)}"
        )

@metrics_router.get(
    "/info",
    summary="Metrics Information",
    description="Get information about available metrics and their descriptions",
    responses={
        200: {
            "description": "Metrics information",
            "content": {
                "application/json": {
                    "example": {
                        "metrics": [
                            {
                                "name": "http_requests_total",
                                "type": "counter",
                                "description": "Total number of HTTP requests",
                                "labels": ["method", "endpoint", "status_code", "version"]
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def get_metrics_info() -> Dict[str, Any]:
    """
    Get information about available metrics.
    
    This endpoint provides metadata about all available metrics including
    their names, types, descriptions, and label information.
    
    Returns:
        Dict[str, Any]: Metrics information
    """
    try:
        registry = get_metrics_registry()
        
        metrics_info = []
        
        for collector in registry._collector_to_names.keys():
            try:
                # Get metric samples
                samples = list(collector.collect())
                
                for sample in samples:
                    metric_info = {
                        "name": sample.name,
                        "type": sample.type,
                        "description": getattr(collector, '_documentation', 'No description available'),
                        "labels": list(sample.labels.keys()) if sample.labels else [],
                        "value": sample.value if hasattr(sample, 'value') else None
                    }
                    
                    # Avoid duplicates
                    if not any(m['name'] == metric_info['name'] for m in metrics_info):
                        metrics_info.append(metric_info)
                        
            except Exception as exc:
                logger.warning(f"Could not collect info for metric {collector}: {exc}")
                continue
        
        return {
            "total_metrics": len(metrics_info),
            "metrics": metrics_info,
            "registry_info": {
                "registry_type": type(registry).__name__,
                "collectors_count": len(registry._collector_to_names)
            }
        }
        
    except Exception as exc:
        logger.error(f"Error getting metrics info: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics info: {str(exc)}"
        )

@metrics_router.post(
    "/reset",
    summary="Reset Metrics",
    description="Reset all metrics to their initial state (use with caution)",
    responses={
        200: {
            "description": "Metrics reset successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "All metrics have been reset",
                        "reset_timestamp": "2024-01-01T00:00:00Z"
                    }
                }
            }
        },
        403: {
            "description": "Reset operation not allowed in production"
        }
    }
)
async def reset_metrics(request: Request) -> Dict[str, Any]:
    """
    Reset all metrics to their initial state.
    
    WARNING: This endpoint should only be used in development/testing
    environments. In production, this could cause loss of important
    monitoring data.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Dict[str, Any]: Reset confirmation
        
    Raises:
        HTTPException: If reset is not allowed or fails
    """
    # Check if this is a production environment
    # In a real implementation, you might check environment variables
    # or other configuration to determine if reset is allowed
    
    # For now, we'll allow it but log a warning
    logger.warning(f"Metrics reset requested from {request.client.host if request.client else 'unknown'}")
    
    try:
        registry = get_metrics_registry()
        
        # Reset all collectors
        for collector in registry._collector_to_names.keys():
            try:
                if hasattr(collector, '_reset'):
                    collector._reset()
                elif hasattr(collector, 'reset'):
                    collector.reset()
            except Exception as exc:
                logger.warning(f"Could not reset collector {collector}: {exc}")
                continue
        
        # Re-initialize metrics
        from .base import setup_metrics
        setup_metrics()
        
        import datetime
        reset_timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        
        logger.info("All metrics have been reset")
        
        return {
            "message": "All metrics have been reset",
            "reset_timestamp": reset_timestamp,
            "warning": "This operation should only be used in development/testing environments"
        }
        
    except Exception as exc:
        logger.error(f"Error resetting metrics: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset metrics: {str(exc)}"
        )
