# apps/core/routers/health.py

from fastapi import APIRouter
from loguru import logger
from conf.enhanced_logging import get_logger, monitor_log_health, get_log_stats
from pathlib import Path

router = APIRouter()
health_logger = get_logger(__name__)

@router.get('/')
def welcome_message():
    return {
        "message": "Welcome to n8n SSO Gateway!",
        "versions": [
            "/v1/docs",
            "/v2/docs",
        ],
        "status": "healthy"
    }


@router.get('/version')
def last_version():
    return {
        "versions": [
            "/v1/docs",
            "/v2/docs",
        ]
    }


@router.get('/logs')
def log_health():
    """Get logging system health and statistics."""
    try:
        health_status = monitor_log_health()
        
        health_logger.info("Log health check requested", extra={
            "log_status": health_status["status"],
            "total_files": health_status.get("stats", {}).get("total_files", 0),
            "total_size_mb": health_status.get("stats", {}).get("total_size_mb", 0)
        })
        
        return {
            "logging_health": health_status,
            "log_directory": str(Path("logs").absolute()),
            "recommendations": {
                "monitor_size": "Keep total log size under 1GB",
                "cleanup_frequency": "Automatic cleanup enabled",
                "compression": "Logs are compressed with gzip",
                "retention": {
                    "app_logs": "7 days",
                    "complete_logs": "14 days", 
                    "error_logs": "90 days",
                    "structured_logs": "21 days",
                    "access_logs": "30 days"
                }
            }
        }
        
    except Exception as exc:
        health_logger.error("Log health check failed", extra={
            "error": str(exc),
            "error_type": type(exc).__name__
        })
        return {
            "logging_health": {
                "status": "error",
                "error": str(exc)
            }
        }
