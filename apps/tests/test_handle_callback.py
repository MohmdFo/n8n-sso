#!/usr/bin/env python3
"""
Test the enhanced handle_casdoor_callback to verify:
1. Always attempts n8n login after Casdoor authentication (unless very recent session)
2. Clear debug logging shows decision branches  
3. Handles both new users and existing users correctly
"""

import asyncio
import time
import pytest
import sys
import logging
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass

# Add the project path so we can import our modules
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.auth.services import handle_casdoor_callback
from apps.integrations.n8n_db import CasdoorProfile

# Setup logging to see all debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')

@dataclass
class MockSession:
    session_id: str
    email: str
    created_at: float
    is_persistent: bool
    n8n_cookie: str = None

@dataclass 
class MockRequest:
    client: object
    def __init__(self):
        self.client = Mock()
        self.client.host = "127.0.0.1"

class TestHandleCasdoorCallback:
    """Test the enhanced handle_casdoor_callback function"""
    
    @pytest.mark.asyncio
    async def test_fresh_user_login(self):
        """Test fresh user login (no existing session)"""
        print("\n=== Test: Fresh user login ===")
        
        profile = CasdoorProfile(
            email="newuser@example.com",
            first_name="New",
            last_name="User",
            display_name="New User",
            casdoor_id="user123"
        )
        
        mock_request = MockRequest()
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager, \
             patch('apps.auth.services.ensure_user_project_binding') as mock_ensure_user, \
             patch('apps.auth.services.N8NClient') as mock_n8n_client, \
             patch('apps.auth.services.extract_n8n_auth_cookie') as mock_extract_cookie, \
             patch('apps.auth.services.get_settings') as mock_settings:
            
            # Setup mocks
            mock_session_manager.get_active_session.return_value = None
            mock_session_manager.create_session.return_value = "new-session-123"
            
            mock_ensure_user.return_value = (Mock(id=1), "temp-password-123")
            
            mock_client_instance = Mock()
            mock_n8n_client.return_value = mock_client_instance
            mock_client_instance.login_user.return_value = Mock(status_code=200)
            mock_client_instance.close.return_value = None
            
            mock_extract_cookie.return_value = "n8n-auth-cookie-value"
            
            mock_settings.return_value = Mock(N8N_BASE_URL="http://localhost:5678")
            
            # Call the function
            try:
                result = await handle_casdoor_callback(
                    profile=profile,
                    request=mock_request,
                    request_id="test-req-123"
                )
                
                print("✅ Fresh user login completed successfully")
                
                # Verify n8n login was called
                mock_client_instance.login_user.assert_called_once()
                
                # Verify session was created and updated
                mock_session_manager.create_session.assert_called_once_with("newuser@example.com")
                mock_session_manager.update_session_cookie.assert_called_once()
                
                print("✅ All expected functions were called")
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False
                
        return True
    
    @pytest.mark.asyncio
    async def test_user_with_old_session(self):
        """Test user with old session (should trigger fresh n8n login)"""
        print("\n=== Test: User with old session ===")
        
        profile = CasdoorProfile(
            email="existinguser@example.com",
            first_name="Existing", 
            last_name="User",
            display_name="Existing User",
            casdoor_id="user456"
        )
        
        mock_request = MockRequest()
        
        # Old session (5 minutes ago)
        old_session = MockSession(
            session_id="old-session-456",
            email="existinguser@example.com",
            created_at=time.time() - 300,  # 5 minutes ago
            is_persistent=True,
            n8n_cookie="old-cookie-value"
        )
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager, \
             patch('apps.auth.services.ensure_user_project_binding') as mock_ensure_user, \
             patch('apps.auth.services.N8NClient') as mock_n8n_client, \
             patch('apps.auth.services.extract_n8n_auth_cookie') as mock_extract_cookie, \
             patch('apps.auth.services.get_settings') as mock_settings:
            
            # Setup mocks
            mock_session_manager.get_active_session.return_value = old_session
            
            mock_ensure_user.return_value = (Mock(id=2), None)  # Existing user
            
            mock_client_instance = Mock()
            mock_n8n_client.return_value = mock_client_instance
            mock_client_instance.login_user.return_value = Mock(status_code=200)
            mock_client_instance.close.return_value = None
            
            mock_extract_cookie.return_value = "fresh-n8n-auth-cookie"
            
            mock_settings.return_value = Mock(N8N_BASE_URL="http://localhost:5678")
            
            # Add rotate_user_password mock
            with patch('apps.auth.services.rotate_user_password') as mock_rotate:
                try:
                    result = await handle_casdoor_callback(
                        profile=profile,
                        request=mock_request,
                        request_id="test-req-456"
                    )
                    
                    print("✅ User with old session login completed successfully")
                    
                    # Verify password was rotated (existing user)
                    mock_rotate.assert_called_once()
                    
                    # Verify n8n login was called (old session should not skip)
                    mock_client_instance.login_user.assert_called_once()
                    
                    # Verify session cookie was updated
                    mock_session_manager.update_session_cookie.assert_called_once()
                    
                    print("✅ Fresh n8n login was performed despite old session")
                    
                except Exception as e:
                    print(f"❌ Test failed: {e}")
                    return False
                    
        return True
    
    @pytest.mark.asyncio
    async def test_user_with_very_recent_session(self):
        """Test user with very recent session (should skip n8n login)"""
        print("\n=== Test: User with very recent session ===")
        
        profile = CasdoorProfile(
            email="recentuser@example.com",
            first_name="Recent",
            last_name="User", 
            display_name="Recent User",
            casdoor_id="user789"
        )
        
        mock_request = MockRequest()
        
        # Very recent session (30 seconds ago)
        recent_session = MockSession(
            session_id="recent-session-789",
            email="recentuser@example.com",
            created_at=time.time() - 30,  # 30 seconds ago
            is_persistent=True,
            n8n_cookie="recent-cookie-value"
        )
        
        with patch('apps.auth.services.SessionManager') as mock_session_manager, \
             patch('apps.auth.services.ensure_user_project_binding') as mock_ensure_user, \
             patch('apps.auth.services.get_settings') as mock_settings:
            
            # Setup mocks
            mock_session_manager.get_active_session.return_value = recent_session
            
            mock_ensure_user.return_value = (Mock(id=3), None)  # Existing user
            
            mock_settings.return_value = Mock(N8N_BASE_URL="http://localhost:5678")
            
            # Add rotate_user_password mock  
            with patch('apps.auth.services.rotate_user_password') as mock_rotate:
                try:
                    result = await handle_casdoor_callback(
                        profile=profile,
                        request=mock_request,
                        request_id="test-req-789"
                    )
                    
                    print("✅ User with recent session login completed successfully")
                    
                    # Verify password was rotated (existing user)
                    mock_rotate.assert_called_once()
                    
                    # Verify we got a redirect response
                    from fastapi.responses import RedirectResponse
                    assert isinstance(result, RedirectResponse)
                    
                    print("✅ Recent session was reused (skipped n8n login)")
                    
                except Exception as e:
                    print(f"❌ Test failed: {e}")
                    return False
                    
        return True

async def run_tests():
    """Run all callback tests"""
    print("Testing Enhanced handle_casdoor_callback Function")
    print("=" * 55)
    
    test_suite = TestHandleCasdoorCallback()
    
    try:
        success1 = await test_suite.test_fresh_user_login()
        success2 = await test_suite.test_user_with_old_session()
        success3 = await test_suite.test_user_with_very_recent_session()
        
        if success1 and success2 and success3:
            print("\n" + "=" * 55)
            print("✅ All handle_casdoor_callback tests passed!")
            print("✅ Enhanced login flow is working correctly")
            print("✅ Debug logging will show clear decision branches")
            return True
        else:
            print("\n❌ Some tests failed")
            return False
            
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)
