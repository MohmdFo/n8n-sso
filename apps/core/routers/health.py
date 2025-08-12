# apps/core/routers/health.py

from fastapi import APIRouter
from loguru import logger

router = APIRouter()

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
