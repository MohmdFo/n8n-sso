# apps/main.py

import logging
from fastapi import FastAPI
from fastapi_pagination import add_pagination
from fastapi_versioning import VersionedFastAPI

from apps.core.routers.health import router as health_router
from apps.metrics import metrics_router, setup_metrics
from apps.metrics.middleware import PrometheusMetricsMiddleware, MetricsContextMiddleware

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="N8N SSO Gateway",
    description="SSO Gateway for N8N using Casdoor integration",
    version="v1.0.0",
)

# Add metrics middleware (must be added before other middleware)
app.add_middleware(PrometheusMetricsMiddleware, app_name="n8n-sso-gateway")
app.add_middleware(MetricsContextMiddleware)

# Include the n8n_auth endpoints with a prefix and tag
app.include_router(health_router, tags=["Health"])
app.include_router(metrics_router, tags=["Monitoring"])

# Add any middleware, exception handlers, etc. here
add_pagination(app)

# API Versioning: endpoints will be available under /v1, /v2, etc.
app = VersionedFastAPI(app,
                       version_format="{major}",
                       prefix_format="/v{major}",
                       enable_latest=True,
                       default_version=(1, 0))

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    try:
        # Setup Prometheus metrics
        setup_metrics()
        logger.info("Prometheus metrics system initialized successfully")
    except Exception as exc:
        logger.error(f"Failed to initialize metrics system: {exc}")
        # Don't fail startup for metrics issues

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("Application shutting down")
