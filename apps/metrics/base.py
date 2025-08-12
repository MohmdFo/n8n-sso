"""
Prometheus Metrics Definitions for n8n SSO Gateway

This module defines all the Prometheus metrics used throughout the application.
Metrics follow Prometheus naming conventions and include proper labeling for
effective monitoring and alerting.

Metrics Categories:
- HTTP Request Metrics (counters, histograms)
- Authentication Metrics (success/failure counters)
- Business Logic Metrics (user operations, API calls)
- Error Metrics (error counters by type)
- Service Health Metrics (gauges)
"""

import time
from typing import Dict, Any, Optional
from prometheus_client import (
    Counter, Histogram, Gauge, Info, generate_latest,
    CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY
)

# Create a custom registry for the application
REGISTRY = CollectorRegistry()

# HTTP Request Metrics
REQUEST_COUNTER = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code', 'version'],
    registry=REGISTRY
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'version'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
    registry=REGISTRY
)

# Authentication Metrics
AUTH_SUCCESS_COUNTER = Counter(
    'auth_success_total',
    'Total number of successful authentications',
    ['provider', 'user_type', 'method'],
    registry=REGISTRY
)

AUTH_FAILURE_COUNTER = Counter(
    'auth_failure_total',
    'Total number of failed authentications',
    ['provider', 'user_type', 'method', 'reason'],
    registry=REGISTRY
)

# Business Logic Metrics
USER_OPERATION_COUNTER = Counter(
    'user_operations_total',
    'Total number of user operations',
    ['operation_type', 'user_type', 'status'],
    registry=REGISTRY
)

API_CALL_COUNTER = Counter(
    'api_calls_total',
    'Total number of external API calls',
    ['api_name', 'endpoint', 'status', 'method'],
    registry=REGISTRY
)

# Error Metrics
ERROR_COUNTER = Counter(
    'errors_total',
    'Total number of errors',
    ['error_type', 'endpoint', 'severity'],
    registry=REGISTRY
)

# Service Health Metrics
SERVICE_HEALTH_GAUGE = Gauge(
    'service_health_status',
    'Current health status of the service (1 = healthy, 0 = unhealthy)',
    ['service_name', 'component'],
    registry=REGISTRY
)

# Database Connection Metrics
DB_CONNECTION_GAUGE = Gauge(
    'database_connections_active',
    'Number of active database connections',
    ['database_name', 'pool_name'],
    registry=REGISTRY
)

# Redis Metrics
REDIS_OPERATION_COUNTER = Counter(
    'redis_operations_total',
    'Total number of Redis operations',
    ['operation_type', 'status'],
    registry=REGISTRY
)

REDIS_MEMORY_USAGE = Gauge(
    'redis_memory_bytes',
    'Redis memory usage in bytes',
    ['instance'],
    registry=REGISTRY
)

# JWT Token Metrics
JWT_TOKEN_COUNTER = Counter(
    'jwt_tokens_total',
    'Total number of JWT tokens processed',
    ['operation', 'status'],
    registry=REGISTRY
)

# Application Info
APP_INFO = Info(
    'app',
    'Application information',
    registry=REGISTRY
)

def setup_metrics() -> None:
    """
    Initialize and configure all metrics.
    
    This function sets up initial values for gauges and info metrics.
    Should be called during application startup.
    """
    # Set application info
    APP_INFO.info({
        'name': 'n8n-sso-gateway',
        'version': '1.0.0',
        'description': 'SSO Gateway for n8n using Casdoor integration'
    })
    
    # Initialize service health to healthy
    SERVICE_HEALTH_GAUGE.labels(
        service_name='n8n-sso-gateway',
        component='main'
    ).set(1)
    
    # Initialize database connection gauge
    DB_CONNECTION_GAUGE.labels(
        database_name='postgresql',
        pool_name='default'
    ).set(0)
    
    # Initialize Redis memory usage
    REDIS_MEMORY_USAGE.labels(instance='default').set(0)

def get_metrics_registry() -> CollectorRegistry:
    """
    Get the application's Prometheus metrics registry.
    
    Returns:
        CollectorRegistry: The metrics registry containing all application metrics
    """
    return REGISTRY

def record_request_metrics(
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
    version: str = "v1"
) -> None:
    """
    Record HTTP request metrics.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        status_code: HTTP status code
        duration: Request duration in seconds
        version: API version
    """
    REQUEST_COUNTER.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_code,
        version=version
    ).inc()
    
    REQUEST_DURATION.labels(
        method=method,
        endpoint=endpoint,
        version=version
    ).observe(duration)

def record_auth_success(
    provider: str,
    user_type: str,
    method: str
) -> None:
    """
    Record successful authentication.
    
    Args:
        provider: Authentication provider (casdoor, etc.)
        user_type: Type of user (admin, regular, etc.)
        method: Authentication method (password, oauth, etc.)
    """
    AUTH_SUCCESS_COUNTER.labels(
        provider=provider,
        user_type=user_type,
        method=method
    ).inc()

def record_auth_failure(
    provider: str,
    user_type: str,
    method: str,
    reason: str
) -> None:
    """
    Record failed authentication.
    
    Args:
        provider: Authentication provider
        user_type: Type of user
        method: Authentication method
        reason: Reason for failure
    """
    AUTH_FAILURE_COUNTER.labels(
        provider=provider,
        user_type=user_type,
        method=method,
        reason=reason
    ).inc()

def record_user_operation(
    operation_type: str,
    user_type: str,
    status: str
) -> None:
    """
    Record user operation metrics.
    
    Args:
        operation_type: Type of operation (create, update, delete, etc.)
        user_type: Type of user performing the operation
        status: Status of the operation (success, failure, etc.)
    """
    USER_OPERATION_COUNTER.labels(
        operation_type=operation_type,
        user_type=user_type,
        status=status
    ).inc()

def record_api_call(
    api_name: str,
    endpoint: str,
    status: str,
    method: str
) -> None:
    """
    Record external API call metrics.
    
    Args:
        api_name: Name of the external API
        endpoint: API endpoint
        status: Call status (success, failure, timeout, etc.)
        method: HTTP method used
    """
    API_CALL_COUNTER.labels(
        api_name=api_name,
        endpoint=endpoint,
        status=status,
        method=method
    ).inc()

def record_error(
    error_type: str,
    endpoint: str,
    severity: str = "medium"
) -> None:
    """
    Record error metrics.
    
    Args:
        error_type: Type of error (validation, authentication, database, etc.)
        endpoint: Endpoint where the error occurred
        severity: Error severity (low, medium, high, critical)
    """
    ERROR_COUNTER.labels(
        error_type=error_type,
        endpoint=endpoint,
        severity=severity
    ).inc()

def update_service_health(
    service_name: str,
    component: str,
    is_healthy: bool
) -> None:
    """
    Update service health status.
    
    Args:
        service_name: Name of the service
        component: Component being monitored
        is_healthy: Whether the service is healthy
    """
    SERVICE_HEALTH_GAUGE.labels(
        service_name=service_name,
        component=component
    ).set(1 if is_healthy else 0)

def update_db_connections(
    database_name: str,
    pool_name: str,
    connection_count: int
) -> None:
    """
    Update database connection count.
    
    Args:
        database_name: Name of the database
        pool_name: Name of the connection pool
        connection_count: Number of active connections
    """
    DB_CONNECTION_GAUGE.labels(
        database_name=database_name,
        pool_name=pool_name
    ).set(connection_count)

def record_redis_operation(
    operation_type: str,
    status: str
) -> None:
    """
    Record Redis operation metrics.
    
    Args:
        operation_type: Type of Redis operation (get, set, delete, etc.)
        status: Operation status (success, failure, timeout)
    """
    REDIS_OPERATION_COUNTER.labels(
        operation_type=operation_type,
        status=status
    ).inc()

def update_redis_memory(
    instance: str,
    memory_bytes: int
) -> None:
    """
    Update Redis memory usage.
    
    Args:
        instance: Redis instance identifier
        memory_bytes: Memory usage in bytes
    """
    REDIS_MEMORY_USAGE.labels(instance=instance).set(memory_bytes)

def record_jwt_token(
    operation: str,
    status: str
) -> None:
    """
    Record JWT token operation metrics.
    
    Args:
        operation: JWT operation (create, validate, refresh, etc.)
        status: Operation status (success, failure, expired, etc.)
    """
    JWT_TOKEN_COUNTER.labels(
        operation=operation,
        status=status
    ).inc()

def generate_metrics_response() -> tuple[bytes, str]:
    """
    Generate Prometheus metrics response.
    
    Returns:
        tuple: (metrics_data, content_type)
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
