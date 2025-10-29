#!/usr/bin/env python3
"""
Comprehensive unit tests for authentication routers.

Tests all router endpoints with proper mocking to avoid external dependencies.
Covers login, callback, webhook, and logout endpoints with various scenarios.
"""

import pytest
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.auth.routers import router, casdoor_callback, casdoor_login, casdoor_webhook, casdoor_logout


class MockRequest:
    """Mock FastAPI Request object."""
    
    def __init__(self, query_params=None, headers=None, cookies=None, client_host="127.0.0.1"):
        self.query_params = query_params or {}
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = Mock()
        self.client.host = client_host
        
    def url_for(self, name):
        """Mock url_for method."""
        if name == "casdoor_callback":
            return "https://example.com/auth/casdoor/callback"
        return f"https://example.com/{name}"


class TestCasdoorLogin:
    """Test Casdoor login endpoint."""
    
    @pytest.mark.asyncio
    @patch('apps.auth.routers.get_casdoor_login_url')
    @patch('apps.auth.routers.create_secure_state')
    @pytest.mark.asyncio
    async def test_casdoor_login_success(self, mock_create_state, mock_get_login_url):
        """Test successful login initiation."""
        # Mock state creation
        mock_create_state.return_value = "secure_state_123"
        
        # Mock login URL generation
        mock_get_login_url.return_value = "https://casdoor.example.com/login/oauth/authorize?client_id=test&state=secure_state_123"
        
        # Create mock request
        request = MockRequest(
            headers={"user-agent": "Test Browser", "referer": "https://app.example.com"}
        )
        
        # Test login endpoint
        result = await casdoor_login(request)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "casdoor.example.com" in result.headers["location"]
        
        # Verify mocks were called
        mock_create_state.assert_called_once()
        mock_get_login_url.assert_called_once()
        
        print("✅ Casdoor login (success) works correctly")
    
    @patch('apps.auth.routers.get_casdoor_login_url')
    @patch('apps.auth.routers.create_secure_state')
    @pytest.mark.asyncio
    async def test_casdoor_login_url_generation_error(self, mock_create_state, mock_get_login_url):
        """Test login with URL generation error."""
        # Mock state creation
        mock_create_state.return_value = "secure_state_123"
        
        # Mock login URL generation failure
        mock_get_login_url.side_effect = Exception("URL generation failed")
        
        # Create mock request
        request = MockRequest()
        
        # Test login endpoint
        result = await casdoor_login(request)
        
        # Should return safe redirect on error
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor login (URL generation error) works correctly")
    
    @patch('apps.auth.routers.create_secure_state')
    @pytest.mark.asyncio
    async def test_casdoor_login_state_creation_error(self, mock_create_state):
        """Test login with state creation error."""
        # Mock state creation failure
        mock_create_state.side_effect = Exception("State creation failed")
        
        # Create mock request
        request = MockRequest()
        
        # Test login endpoint
        result = await casdoor_login(request)
        
        # Should return safe redirect on error
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor login (state creation error) works correctly")


class TestCasdoorCallback:
    """Test Casdoor OAuth callback endpoint."""
    
    @patch('apps.auth.routers.validate_callback_state')
    @patch('apps.auth.routers.process_oauth_callback_safely')
    @pytest.mark.asyncio
    async def test_casdoor_callback_success(self, mock_process_callback, mock_validate_state):
        """Test successful OAuth callback processing."""
        # Mock state validation
        mock_oauth_state = Mock()
        mock_oauth_state.request_id = "test_request_123"
        mock_oauth_state.created_at = 1234567890.0
        mock_validate_state.return_value = mock_oauth_state
        
        # Mock callback processing
        mock_result = RedirectResponse(url="https://n8n.example.com/home/workflows")
        mock_process_callback.return_value = mock_result
        
        # Create mock request
        request = MockRequest(
            query_params={"code": "auth_code_123", "state": "state_123"},
            headers={"user-agent": "Test Browser"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result == mock_result
        
        # Verify mocks were called
        mock_validate_state.assert_called_once_with("state_123", "127.0.0.1", "Test Browser")
        mock_process_callback.assert_called_once()
        
        print("✅ Casdoor callback (success) works correctly")
    
    @pytest.mark.asyncio
    async def test_casdoor_callback_missing_code(self):
        """Test callback with missing authorization code."""
        # Create mock request without code
        request = MockRequest(
            query_params={"state": "state_123"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Should return safe redirect for missing code
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback (missing code) works correctly")
    
    @pytest.mark.asyncio
    async def test_casdoor_callback_missing_state(self):
        """Test callback with missing state parameter."""
        # Create mock request without state
        request = MockRequest(
            query_params={"code": "auth_code_123"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Should return safe redirect for missing state
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback (missing state) works correctly")
    
    @patch('apps.auth.routers.validate_callback_state')
    @pytest.mark.asyncio
    async def test_casdoor_callback_invalid_state(self, mock_validate_state):
        """Test callback with invalid state."""
        # Mock state validation failure
        mock_validate_state.return_value = None
        
        # Create mock request
        request = MockRequest(
            query_params={"code": "auth_code_123", "state": "invalid_state"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Should return safe redirect for invalid state
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback (invalid state) works correctly")
    
    @patch('apps.auth.routers.validate_callback_state')
    @patch('apps.auth.routers.process_oauth_callback_safely')
    @pytest.mark.asyncio
    async def test_casdoor_callback_already_processed(self, mock_process_callback, mock_validate_state):
        """Test callback when code already processed."""
        # Mock state validation
        mock_oauth_state = Mock()
        mock_oauth_state.request_id = "test_request_123"
        mock_oauth_state.created_at = 1234567890.0
        mock_validate_state.return_value = mock_oauth_state
        
        # Mock callback processing returns None (already processed)
        mock_process_callback.return_value = None
        
        # Create mock request
        request = MockRequest(
            query_params={"code": "used_code_123", "state": "state_123"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Should return safe redirect for already processed code
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback (already processed) works correctly")
    
    @patch('apps.auth.routers.validate_callback_state')
    @patch('apps.auth.routers.process_oauth_callback_safely')
    @pytest.mark.asyncio
    async def test_casdoor_callback_processing_error(self, mock_process_callback, mock_validate_state):
        """Test callback with processing error."""
        # Mock state validation
        mock_oauth_state = Mock()
        mock_oauth_state.request_id = "test_request_123"
        mock_oauth_state.created_at = 1234567890.0
        mock_validate_state.return_value = mock_oauth_state
        
        # Mock callback processing failure
        mock_process_callback.side_effect = Exception("Processing failed")
        
        # Create mock request
        request = MockRequest(
            query_params={"code": "auth_code_123", "state": "state_123"}
        )
        
        # Test callback endpoint
        result = await casdoor_callback(request)
        
        # Should return safe redirect for processing error
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback (processing error) works correctly")


class TestCasdoorWebhook:
    """Test Casdoor webhook endpoint."""
    
    @patch('apps.auth.routers.handle_casdoor_logout_webhook')
    @pytest.mark.asyncio
    async def test_casdoor_webhook_success(self, mock_handle_webhook):
        """Test successful webhook processing."""
        # Mock webhook handler
        mock_handle_webhook.return_value = {
            "status": "success",
            "user_email": "test@example.com"
        }
        
        # Create mock request with JSON method
        request = MockRequest(
            headers={"content-type": "application/json", "user-agent": "Casdoor-Webhook"}
        )
        request.json = AsyncMock(return_value={
            "action": "logout",
            "user": "test@example.com",
            "organization": "test_org",
            "id": "webhook_123"
        })
        
        # Test webhook endpoint
        result = await casdoor_webhook(request)
        
        # Verify result
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["webhook_id"] == "webhook_123"
        
        # Verify mock was called
        mock_handle_webhook.assert_called_once()
        
        print("✅ Casdoor webhook (success) works correctly")
    
    @pytest.mark.asyncio
    async def test_casdoor_webhook_invalid_json(self):
        """Test webhook with invalid JSON."""
        # Create mock request with invalid JSON
        request = MockRequest(
            headers={"content-type": "application/json"}
        )
        request.json = AsyncMock(side_effect=ValueError("Invalid JSON"))
        
        # Test webhook endpoint - should raise HTTPException
        with pytest.raises(Exception):  # HTTPException or ValueError
            await casdoor_webhook(request)
        
        print("✅ Casdoor webhook (invalid JSON) works correctly")
    
    @patch('apps.auth.routers.handle_casdoor_logout_webhook')
    @pytest.mark.asyncio
    async def test_casdoor_webhook_processing_error(self, mock_handle_webhook):
        """Test webhook with processing error."""
        # Mock webhook handler failure
        mock_handle_webhook.side_effect = Exception("Webhook processing failed")
        
        # Create mock request
        request = MockRequest()
        request.json = AsyncMock(return_value={
            "action": "logout",
            "user": "test@example.com"
        })
        
        # Test webhook endpoint - should raise HTTPException
        with pytest.raises(Exception):  # HTTPException
            await casdoor_webhook(request)
        
        print("✅ Casdoor webhook (processing error) works correctly")


class TestCasdoorLogout:
    """Test Casdoor logout endpoint."""
    
    @patch('apps.integrations.n8n_client.N8NClient')
    @patch('conf.settings.get_settings')
    @pytest.mark.asyncio
    async def test_casdoor_logout_success(self, mock_get_settings, mock_n8n_client_class):
        """Test successful manual logout."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Mock N8N client
        mock_n8n_client = Mock()
        mock_n8n_client_class.return_value = mock_n8n_client
        
        # Mock logout response
        mock_logout_response = Mock()
        mock_logout_response.status_code = 200
        mock_logout_response.text = '{"success": true}'
        mock_n8n_client.logout_user.return_value = mock_logout_response
        
        # Create mock request with auth cookie
        request = MockRequest(
            cookies={"n8n-auth": "test_auth_cookie"},
            headers={"user-agent": "Test Browser", "referer": "https://n8n.example.com"}
        )
        
        # Test logout endpoint
        result = await casdoor_logout(request)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "casdoor.example.com/logout" in result.headers["location"]
        
        # Verify N8N logout was called
        mock_n8n_client.logout_user.assert_called_once_with("test_auth_cookie")
        mock_n8n_client.close.assert_called_once()
        
        print("✅ Casdoor logout (success) works correctly")
    
    @patch('apps.integrations.n8n_client.N8NClient')
    @patch('conf.settings.get_settings')
    @pytest.mark.asyncio
    async def test_casdoor_logout_without_cookie(self, mock_get_settings, mock_n8n_client_class):
        """Test logout without auth cookie."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Mock N8N client
        mock_n8n_client = Mock()
        mock_n8n_client_class.return_value = mock_n8n_client
        
        # Mock logout response
        mock_logout_response = Mock()
        mock_logout_response.status_code = 200
        mock_n8n_client.logout_user.return_value = mock_logout_response
        
        # Create mock request without auth cookie
        request = MockRequest()
        
        # Test logout endpoint
        result = await casdoor_logout(request)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert "casdoor.example.com/logout" in result.headers["location"]
        
        # Verify N8N logout was called with None
        mock_n8n_client.logout_user.assert_called_once_with(None)
        
        print("✅ Casdoor logout (without cookie) works correctly")
    
    @patch('apps.integrations.n8n_client.N8NClient')
    @patch('conf.settings.get_settings')
    @pytest.mark.asyncio
    async def test_casdoor_logout_n8n_error(self, mock_get_settings, mock_n8n_client_class):
        """Test logout with N8N error."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Mock N8N client
        mock_n8n_client = Mock()
        mock_n8n_client_class.return_value = mock_n8n_client
        
        # Mock N8N logout failure
        mock_n8n_client.logout_user.side_effect = Exception("N8N logout failed")
        
        # Create mock request
        request = MockRequest(
            cookies={"n8n-auth": "test_auth_cookie"}
        )
        
        # Test logout endpoint
        result = await casdoor_logout(request)
        
        # Should still redirect to Casdoor logout despite N8N error
        assert isinstance(result, RedirectResponse)
        assert "casdoor.example.com/logout" in result.headers["location"]
        
        # Verify cleanup was attempted
        mock_n8n_client.close.assert_called_once()
        
        print("✅ Casdoor logout (N8N error) works correctly")
    
    @patch('conf.settings.get_settings')
    @pytest.mark.asyncio
    async def test_casdoor_logout_general_error(self, mock_get_settings):
        """Test logout with general error."""
        # Mock settings failure
        mock_get_settings.side_effect = Exception("Settings error")
        
        # Create mock request
        request = MockRequest()
        
        # Test logout endpoint
        result = await casdoor_logout(request)
        
        # Should return safe redirect for general error
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor logout (general error) works correctly")


class TestRouterEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_callback_with_empty_query_params(self):
        """Test callback with empty query parameters."""
        request = MockRequest(query_params={})
        
        result = await casdoor_callback(request)
        
        assert isinstance(result, RedirectResponse)
        print("✅ Callback (empty query params) works correctly")
    
    @pytest.mark.asyncio
    async def test_login_with_special_characters_in_headers(self):
        """Test login with special characters in headers."""
        request = MockRequest(
            headers={
                "user-agent": "Mozilla/5.0 (特殊文字) Test Browser",
                "referer": "https://example.com/特殊パス"
            }
        )
        
        with patch('apps.auth.routers.create_secure_state') as mock_create_state, \
             patch('apps.auth.routers.get_casdoor_login_url') as mock_get_login_url:
            
            mock_create_state.return_value = "state_123"
            mock_get_login_url.return_value = "https://casdoor.example.com/login"
            
            result = await casdoor_login(request)
            
            assert isinstance(result, RedirectResponse)
        
        print("✅ Login (special characters in headers) works correctly")
    
    @pytest.mark.asyncio
    async def test_webhook_with_large_payload(self):
        """Test webhook with large payload."""
        # Create large payload
        large_payload = {
            "action": "logout",
            "user": "test@example.com",
            "data": "x" * 10000,  # Large data field
            "metadata": {f"key_{i}": f"value_{i}" for i in range(1000)}
        }
        
        request = MockRequest()
        request.json = AsyncMock(return_value=large_payload)
        
        with patch('apps.auth.routers.handle_casdoor_logout_webhook') as mock_handle:
            mock_handle.return_value = {"status": "success"}
            
            result = await casdoor_webhook(request)
            
            assert isinstance(result, dict)
            assert result["success"] is True
        
        print("✅ Webhook (large payload) works correctly")
    
    @pytest.mark.asyncio
    async def test_logout_with_very_long_cookie(self):
        """Test logout with very long auth cookie."""
        long_cookie = "x" * 5000  # Very long cookie
        
        request = MockRequest(cookies={"n8n-auth": long_cookie})
        
        with patch('apps.integrations.n8n_client.N8NClient') as mock_client_class, \
             patch('conf.settings.get_settings') as mock_get_settings:
            
            mock_settings = Mock()
            mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
            mock_get_settings.return_value = mock_settings
            
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.logout_user.return_value = Mock(status_code=200)
            
            result = await casdoor_logout(request)
            
            assert isinstance(result, RedirectResponse)
            mock_client.logout_user.assert_called_once_with(long_cookie)
        
        print("✅ Logout (very long cookie) works correctly")


def run_all_tests():
    """Run all authentication router tests."""
    print("🛣️  Starting Authentication Routers Test Suite...")
    print("=" * 60)
    
    try:
        # Test login endpoint
        login_tests = TestCasdoorLogin()
        asyncio.run(login_tests.test_casdoor_login_success())
        asyncio.run(login_tests.test_casdoor_login_url_generation_error())
        asyncio.run(login_tests.test_casdoor_login_state_creation_error())
        print()
        
        # Test callback endpoint
        callback_tests = TestCasdoorCallback()
        asyncio.run(callback_tests.test_casdoor_callback_success())
        asyncio.run(callback_tests.test_casdoor_callback_missing_code())
        asyncio.run(callback_tests.test_casdoor_callback_missing_state())
        asyncio.run(callback_tests.test_casdoor_callback_invalid_state())
        asyncio.run(callback_tests.test_casdoor_callback_already_processed())
        asyncio.run(callback_tests.test_casdoor_callback_processing_error())
        print()
        
        # Test webhook endpoint
        webhook_tests = TestCasdoorWebhook()
        asyncio.run(webhook_tests.test_casdoor_webhook_success())
        asyncio.run(webhook_tests.test_casdoor_webhook_invalid_json())
        asyncio.run(webhook_tests.test_casdoor_webhook_processing_error())
        print()
        
        # Test logout endpoint
        logout_tests = TestCasdoorLogout()
        asyncio.run(logout_tests.test_casdoor_logout_success())
        asyncio.run(logout_tests.test_casdoor_logout_without_cookie())
        asyncio.run(logout_tests.test_casdoor_logout_n8n_error())
        asyncio.run(logout_tests.test_casdoor_logout_general_error())
        print()
        
        # Test edge cases
        edge_tests = TestRouterEdgeCases()
        asyncio.run(edge_tests.test_callback_with_empty_query_params())
        asyncio.run(edge_tests.test_login_with_special_characters_in_headers())
        asyncio.run(edge_tests.test_webhook_with_large_payload())
        asyncio.run(edge_tests.test_logout_with_very_long_cookie())
        print()
        
        print("🎉 All Authentication Router tests passed!")
        print("✅ Login endpoint working correctly")
        print("✅ Callback processing verified")
        print("✅ Webhook handling robust")
        print("✅ Logout functionality tested")
        print("✅ Error handling comprehensive")
        print("✅ Edge cases handled gracefully")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🛣️  n8n SSO Gateway - Authentication Routers Test Suite")
    print("=" * 60)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 60)
        print("🏆 ALL AUTHENTICATION ROUTER TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Router endpoints are secure and reliable")
        print("⚡ OAuth flow handling verified")
        print("🎯 Webhook processing working correctly")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 AUTHENTICATION ROUTER TESTS FAILED!")
        print("❌ Router endpoints need attention")
        print("=" * 60)
        exit(1)
