"""
OAuth state management and request deduplication for preventing race conditions.

This module provides mechanisms to:
1. Generate and validate OAuth state parameters for CSRF protection
2. Implement distributed locking for one-time code processing
3. Track and prevent duplicate callback processing
4. Ensure session persistence without overwrites
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Set
from urllib.parse import urlparse

from conf.enhanced_logging import get_logger
from conf.settings import get_settings

logger = get_logger(__name__)

# In-memory stores for state and locks (in production, use Redis or similar)
_oauth_states: Dict[str, 'OAuthState'] = {}
_processing_locks: Dict[str, asyncio.Lock] = {}
_processed_codes: Set[str] = set()
_active_sessions: Dict[str, 'SessionInfo'] = {}

# Cleanup intervals (seconds)
STATE_EXPIRY = 600  # 10 minutes
LOCK_EXPIRY = 120   # 2 minutes  
CODE_BLACKLIST_EXPIRY = 3600  # 1 hour


@dataclass
class OAuthState:
    """OAuth state information for request validation."""
    state_id: str
    user_ip: str
    user_agent: str
    created_at: float
    request_id: str
    callback_url: str
    is_consumed: bool = False
    

@dataclass
class SessionInfo:
    """Information about an active login session."""
    email: str
    session_id: str
    created_at: float
    n8n_cookie: Optional[str] = None
    is_persistent: bool = False


class OAuthStateManager:
    """Manages OAuth state for CSRF protection and deduplication."""
    
    @staticmethod
    def generate_state(request_ip: str, user_agent: str, callback_url: str, request_id: str) -> str:
        """Generate a unique OAuth state parameter."""
        state_id = str(uuid.uuid4())
        
        oauth_state = OAuthState(
            state_id=state_id,
            user_ip=request_ip,
            user_agent=user_agent,
            created_at=time.time(),
            request_id=request_id,
            callback_url=callback_url
        )
        
        _oauth_states[state_id] = oauth_state
        
        logger.info("OAuth state generated", extra={
            "state_id": state_id,
            "request_id": request_id,
            "user_ip": request_ip,
            "callback_url": callback_url
        })
        
        return state_id
    
    @staticmethod
    def validate_state(state_id: str, request_ip: str, user_agent: str) -> Optional[OAuthState]:
        """Validate OAuth state and return state info if valid."""
        if not state_id or state_id not in _oauth_states:
            logger.warning("Invalid OAuth state", extra={
                "state_id": state_id,
                "available_states": len(_oauth_states)
            })
            return None
        
        oauth_state = _oauth_states[state_id]
        current_time = time.time()
        
        # Check expiry
        if current_time - oauth_state.created_at > STATE_EXPIRY:
            logger.warning("Expired OAuth state", extra={
                "state_id": state_id,
                "age": current_time - oauth_state.created_at,
                "expiry": STATE_EXPIRY
            })
            del _oauth_states[state_id]
            return None
        
        # Check if already consumed
        if oauth_state.is_consumed:
            logger.warning("OAuth state already consumed", extra={
                "state_id": state_id,
                "request_id": oauth_state.request_id
            })
            return None
        
        # Validate request context (optional - can be relaxed if needed)
        if oauth_state.user_ip != request_ip:
            logger.warning("OAuth state IP mismatch", extra={
                "state_id": state_id,
                "expected_ip": oauth_state.user_ip,
                "actual_ip": request_ip
            })
            # Don't fail on IP mismatch - user might be behind NAT/proxy
        
        # Mark as consumed
        oauth_state.is_consumed = True
        
        logger.info("OAuth state validated successfully", extra={
            "state_id": state_id,
            "request_id": oauth_state.request_id,
            "age": current_time - oauth_state.created_at
        })
        
        return oauth_state
    
    @staticmethod
    def cleanup_expired_states():
        """Clean up expired OAuth states."""
        current_time = time.time()
        expired_states = [
            state_id for state_id, state in _oauth_states.items()
            if current_time - state.created_at > STATE_EXPIRY
        ]
        
        for state_id in expired_states:
            del _oauth_states[state_id]
        
        if expired_states:
            logger.info("Cleaned up expired OAuth states", extra={
                "expired_count": len(expired_states),
                "remaining_count": len(_oauth_states)
            })


class CallbackProcessor:
    """Handles OAuth callback processing with deduplication and locking."""
    
    @staticmethod
    async def acquire_processing_lock(code: str, timeout: float = 30.0) -> bool:
        """Acquire a lock for processing an OAuth authorization code."""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        
        if code_hash not in _processing_locks:
            _processing_locks[code_hash] = asyncio.Lock()
        
        lock = _processing_locks[code_hash]
        
        try:
            # Try to acquire lock with timeout
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            
            # Check if code was already processed while waiting
            if code_hash in _processed_codes:
                lock.release()
                logger.warning("OAuth code already processed while waiting for lock", extra={
                    "code_hash": code_hash
                })
                return False
            
            logger.info("Processing lock acquired", extra={
                "code_hash": code_hash,
                "timeout": timeout
            })
            return True
            
        except asyncio.TimeoutError:
            logger.error("Failed to acquire processing lock - timeout", extra={
                "code_hash": code_hash,
                "timeout": timeout
            })
            return False
    
    @staticmethod
    def release_processing_lock(code: str, mark_processed: bool = True):
        """Release the processing lock for an OAuth authorization code."""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        
        if code_hash in _processing_locks:
            lock = _processing_locks[code_hash]
            
            if mark_processed:
                _processed_codes.add(code_hash)
                logger.info("OAuth code marked as processed", extra={
                    "code_hash": code_hash
                })
            
            if lock.locked():
                lock.release()
                logger.info("Processing lock released", extra={
                    "code_hash": code_hash,
                    "marked_processed": mark_processed
                })
    
    @staticmethod
    def is_code_processed(code: str) -> bool:
        """Check if an OAuth authorization code has already been processed."""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        return code_hash in _processed_codes
    
    @staticmethod
    def cleanup_processed_codes():
        """Clean up old processed codes to prevent memory leaks."""
        # In a real implementation, this would check timestamps
        # For now, we'll limit the size of the set
        if len(_processed_codes) > 10000:
            # Remove oldest half (in production, use a time-based cleanup)
            codes_to_remove = list(_processed_codes)[:5000]
            for code_hash in codes_to_remove:
                _processed_codes.discard(code_hash)
            
            logger.info("Cleaned up processed codes", extra={
                "removed_count": len(codes_to_remove),
                "remaining_count": len(_processed_codes)
            })


class SessionManager:
    """Manages user sessions to prevent overwrites and ensure persistence."""
    
    @staticmethod
    def create_session(email: str, n8n_cookie: Optional[str] = None) -> str:
        """Create a new session for a user."""
        session_id = str(uuid.uuid4())
        
        session_info = SessionInfo(
            email=email,
            session_id=session_id,
            created_at=time.time(),
            n8n_cookie=n8n_cookie,
            is_persistent=n8n_cookie is not None
        )
        
        # Check for existing active session
        existing_session = SessionManager.get_active_session(email)
        if existing_session and existing_session.is_persistent:
            logger.warning("User already has persistent session", extra={
                "email": email,
                "existing_session_id": existing_session.session_id,
                "new_session_id": session_id
            })
            # Return existing session ID to prevent overwrite
            return existing_session.session_id
        
        _active_sessions[session_id] = session_info
        
        logger.info("Session created", extra={
            "email": email,
            "session_id": session_id,
            "has_cookie": n8n_cookie is not None,
            "is_persistent": session_info.is_persistent
        })
        
        return session_id
    
    @staticmethod
    def get_active_session(email: str) -> Optional[SessionInfo]:
        """Get the active session for a user."""
        for session_info in _active_sessions.values():
            if session_info.email == email:
                return session_info
        return None
    
    @staticmethod
    def update_session_cookie(session_id: str, n8n_cookie: str) -> bool:
        """Update session with n8n cookie."""
        if session_id not in _active_sessions:
            logger.warning("Session not found for cookie update", extra={
                "session_id": session_id
            })
            return False
        
        session_info = _active_sessions[session_id]
        session_info.n8n_cookie = n8n_cookie
        session_info.is_persistent = True
        
        logger.info("Session cookie updated", extra={
            "session_id": session_id,
            "email": session_info.email,
            "cookie_length": len(n8n_cookie)
        })
        
        return True
    
    @staticmethod
    def is_session_persistent(session_id: str) -> bool:
        """Check if a session has a persistent n8n cookie."""
        session_info = _active_sessions.get(session_id)
        return session_info is not None and session_info.is_persistent
    
    @staticmethod
    def cleanup_expired_sessions():
        """Clean up expired sessions."""
        current_time = time.time()
        session_expiry = 3600  # 1 hour
        
        expired_sessions = [
            session_id for session_id, session_info in _active_sessions.items()
            if current_time - session_info.created_at > session_expiry
        ]
        
        for session_id in expired_sessions:
            del _active_sessions[session_id]
        
        if expired_sessions:
            logger.info("Cleaned up expired sessions", extra={
                "expired_count": len(expired_sessions),
                "remaining_count": len(_active_sessions)
            })


async def cleanup_oauth_data():
    """Periodic cleanup of OAuth data structures."""
    logger.info("Starting OAuth data cleanup")
    
    OAuthStateManager.cleanup_expired_states()
    CallbackProcessor.cleanup_processed_codes() 
    SessionManager.cleanup_expired_sessions()
    
    logger.info("OAuth data cleanup completed")


# Utility functions for easier integration
def create_secure_state(request_ip: str, user_agent: str, callback_url: str, request_id: str) -> str:
    """Create a secure OAuth state parameter."""
    return OAuthStateManager.generate_state(request_ip, user_agent, callback_url, request_id)


def validate_callback_state(state: str, request_ip: str, user_agent: str) -> Optional[OAuthState]:
    """Validate an OAuth callback state parameter."""
    return OAuthStateManager.validate_state(state, request_ip, user_agent)


async def process_oauth_callback_safely(code: str, callback_func, *args, **kwargs):
    """
    Safely process an OAuth callback with deduplication and locking.
    
    Args:
        code: OAuth authorization code
        callback_func: Function to call for processing
        *args, **kwargs: Arguments to pass to callback_func
    
    Returns:
        Result from callback_func or None if already processed
    """
    # Check if already processed
    if CallbackProcessor.is_code_processed(code):
        logger.warning("OAuth code already processed - ignoring duplicate", extra={
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16]
        })
        return None
    
    # Acquire processing lock
    if not await CallbackProcessor.acquire_processing_lock(code):
        logger.error("Failed to acquire processing lock for OAuth code")
        return None
    
    try:
        # Process the callback
        result = await callback_func(*args, **kwargs)
        
        # Mark as successfully processed
        CallbackProcessor.release_processing_lock(code, mark_processed=True)
        
        return result
        
    except Exception as exc:
        # Release lock without marking as processed (allow retry)
        CallbackProcessor.release_processing_lock(code, mark_processed=False)
        raise exc
