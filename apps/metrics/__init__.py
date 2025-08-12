"""
Prometheus Metrics Module for Dify SSO Gateway

This module provides comprehensive monitoring and metrics collection for the FastAPI application.
It includes request tracking, performance monitoring, business metrics, and health indicators.

Exports:
    - metrics_router: FastAPI router for the /metrics endpoint
    - get_metrics_registry: Function to get the Prometheus registry
    - setup_metrics: Function to initialize metrics collection
"""

from .routers import metrics_router
from .base import (
    REQUEST_COUNTER,
    REQUEST_DURATION,
    AUTH_SUCCESS_COUNTER,
    AUTH_FAILURE_COUNTER,
    USER_OPERATION_COUNTER,
    API_CALL_COUNTER,
    ERROR_COUNTER,
    SERVICE_HEALTH_GAUGE,
    get_metrics_registry,
    setup_metrics
)

__all__ = [
    "metrics_router",
    "REQUEST_COUNTER",
    "REQUEST_DURATION", 
    "AUTH_SUCCESS_COUNTER",
    "AUTH_FAILURE_COUNTER",
    "USER_OPERATION_COUNTER",
    "API_CALL_COUNTER",
    "ERROR_COUNTER",
    "SERVICE_HEALTH_GAUGE",
    "get_metrics_registry",
    "setup_metrics"
]

__version__ = "1.0.0"
