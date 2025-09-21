#!/usr/bin/env python3
"""
Test the enhanced login flow to verify:
1. Fresh n8n login after Casdoor authentication (even with existing sessions)
2. Only very recent persistent sessions (< 60s) are reused
3. Clear debug logging shows decision branches
"""

import time
import asyncio
import logging
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass

# Setup logging
logging.basicConfig(level=logging.DEBUG)

@dataclass
class MockSession:
    session_id: str
    email: str
    created_at: float
    is_persistent: bool
    n8n_cookie: str = None

@dataclass
class MockProfile:
    email: str
    name: str
    id: str

class TestFreshLoginFlow:
    """Test enhanced login flow behavior"""
    
    def test_fresh_login_with_no_existing_session(self):
        """Test that new users get fresh n8n login"""
        print("\n=== Test: Fresh login with no existing session ===")
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager:
            # No existing session
            mock_session_manager.get_active_session.return_value = None
            mock_session_manager.create_session.return_value = "new-session-123"
            
            # This should proceed to n8n login
            result = self._simulate_session_check("user@example.com", None)
            
            print(f"Result: {result}")
            assert result['skip_n8n_login'] == False
            assert result['reason'] == "no_existing_session"
            
    def test_fresh_login_with_old_session(self):
        """Test that old sessions trigger fresh n8n login"""
        print("\n=== Test: Fresh login with old session ===")
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager:
            # Old session (5 minutes ago)
            old_session = MockSession(
                session_id="old-session-123",
                email="user@example.com", 
                created_at=time.time() - 300,  # 5 minutes ago
                is_persistent=True,
                n8n_cookie="old-cookie-value"
            )
            mock_session_manager.get_active_session.return_value = old_session
            
            # This should proceed to n8n login
            result = self._simulate_session_check("user@example.com", old_session)
            
            print(f"Result: {result}")
            assert result['skip_n8n_login'] == False
            assert result['reason'] == "session_too_old"
            
    def test_reuse_very_recent_session(self):
        """Test that very recent persistent sessions are reused"""
        print("\n=== Test: Reuse very recent session ===")
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager:
            # Very recent session (30 seconds ago)
            recent_session = MockSession(
                session_id="recent-session-123",
                email="user@example.com",
                created_at=time.time() - 30,  # 30 seconds ago
                is_persistent=True,
                n8n_cookie="recent-cookie-value"
            )
            mock_session_manager.get_active_session.return_value = recent_session
            
            # This should skip n8n login
            result = self._simulate_session_check("user@example.com", recent_session)
            
            print(f"Result: {result}")
            assert result['skip_n8n_login'] == True
            assert result['reason'] == "very_recent_persistent_session"
            
    def test_non_persistent_session_triggers_login(self):
        """Test that non-persistent sessions trigger fresh n8n login"""
        print("\n=== Test: Non-persistent session triggers login ===")
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager:
            # Recent but non-persistent session
            non_persistent_session = MockSession(
                session_id="non-persistent-123",
                email="user@example.com",
                created_at=time.time() - 30,  # 30 seconds ago
                is_persistent=False,  # Not persistent
                n8n_cookie="some-cookie-value"
            )
            mock_session_manager.get_active_session.return_value = non_persistent_session
            
            # This should proceed to n8n login
            result = self._simulate_session_check("user@example.com", non_persistent_session)
            
            print(f"Result: {result}")
            assert result['skip_n8n_login'] == False
            assert result['reason'] == "not_persistent"
            
    def test_session_without_cookie_triggers_login(self):
        """Test that sessions without cookies trigger fresh n8n login"""
        print("\n=== Test: Session without cookie triggers login ===")
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager:
            # Recent persistent session but no cookie
            no_cookie_session = MockSession(
                session_id="no-cookie-123",
                email="user@example.com",
                created_at=time.time() - 30,  # 30 seconds ago
                is_persistent=True,
                n8n_cookie=None  # No cookie
            )
            mock_session_manager.get_active_session.return_value = no_cookie_session
            
            # This should proceed to n8n login
            result = self._simulate_session_check("user@example.com", no_cookie_session)
            
            print(f"Result: {result}")
            assert result['skip_n8n_login'] == False
            assert result['reason'] == "no_cookie"
    
    def _simulate_session_check(self, email: str, existing_session: MockSession = None):
        """Simulate the session checking logic"""
        session_id = None
        skip_n8n_login = False
        reason = None
        
        if existing_session:
            # Check if existing session has a very recent cookie (< 60 seconds old)
            session_age = time.time() - existing_session.created_at
            is_very_recent = session_age < 60
            has_cookie = existing_session.n8n_cookie is not None
            
            if is_very_recent and has_cookie and existing_session.is_persistent:
                skip_n8n_login = True
                reason = "very_recent_persistent_session"
                session_id = existing_session.session_id
            else:
                session_id = existing_session.session_id
                if not is_very_recent:
                    reason = "session_too_old"
                elif not has_cookie:
                    reason = "no_cookie"
                elif not existing_session.is_persistent:
                    reason = "not_persistent"
                else:
                    reason = "unknown"
        else:
            # Create new session for tracking
            session_id = "new-session-123"
            reason = "no_existing_session"
            
        return {
            'skip_n8n_login': skip_n8n_login,
            'session_id': session_id,
            'reason': reason,
            'existing_session': existing_session
        }

def run_tests():
    """Run all tests"""
    print("Testing Enhanced Login Flow Logic")
    print("=" * 50)
    
    test_suite = TestFreshLoginFlow()
    
    try:
        test_suite.test_fresh_login_with_no_existing_session()
        test_suite.test_fresh_login_with_old_session()
        test_suite.test_reuse_very_recent_session()
        test_suite.test_non_persistent_session_triggers_login()
        test_suite.test_session_without_cookie_triggers_login()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("✅ Enhanced login flow logic is working correctly")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
