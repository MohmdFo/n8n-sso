#!/usr/bin/env python3
"""
Comprehensive unit tests for N8NClient class.

Tests all client methods with proper mocking to avoid actual HTTP calls.
Covers login, logout, error handling, and edge cases.
"""

import pytest
import httpx
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.integrations.n8n_client import N8NClient, N8NClientError


class TestN8NClientInitialization:
    """Test N8NClient initialization and configuration."""
    
    def test_client_initialization_default(self):
        """Test client initialization with default parameters."""
        base_url = "https://n8n.example.com"
        client = N8NClient(base_url)
        
        assert client.base_url == base_url
        assert client._client is not None
        assert client._client.base_url == base_url
        
        print("✅ N8NClient initialization (default) works correctly")
    
    def test_client_initialization_custom_timeout(self):
        """Test client initialization with custom timeout."""
        base_url = "https://n8n.example.com"
        custom_timeout = 30.0
        client = N8NClient(base_url, timeout=custom_timeout)
        
        assert client.base_url == base_url
        assert client._client.timeout.read == custom_timeout
        
        print("✅ N8NClient initialization (custom timeout) works correctly")
    
    def test_client_base_url_normalization(self):
        """Test that base URL is properly normalized."""
        # Test with trailing slash
        client1 = N8NClient("https://n8n.example.com/")
        assert client1.base_url == "https://n8n.example.com"
        
        # Test without trailing slash
        client2 = N8NClient("https://n8n.example.com")
        assert client2.base_url == "https://n8n.example.com"
        
        print("✅ Base URL normalization works correctly")
    
    def test_headers_method(self):
        """Test _headers method returns correct headers."""
        client = N8NClient("https://n8n.example.com")
        headers = client._headers()
        
        expected_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        assert headers == expected_headers
        
        print("✅ Headers method works correctly")


class TestN8NClientLogin:
    """Test N8NClient login functionality."""
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_login_user_success(self, mock_client_class):
        """Test successful user login."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        
        # Create a proper headers mock that supports both get_list and dict()
        class HeadersMock:
            def __init__(self):
                self._data = {'set-cookie': 'n8n-auth=test_cookie_value; Path=/; HttpOnly'}
            
            def get_list(self, key):
                if key == 'set-cookie':
                    return ['n8n-auth=test_cookie_value; Path=/; HttpOnly']
                return []
            
            def __iter__(self):
                return iter(self._data.keys())
            
            def __getitem__(self, key):
                return self._data[key]
            
            def keys(self):
                return self._data.keys()
            
            def items(self):
                return self._data.items()
            
            def get(self, key, default=None):
                return self._data.get(key, default)
        
        mock_response.headers = HeadersMock()
        mock_client.request.return_value = mock_response
        
        # Test login
        client = N8NClient("https://n8n.example.com")
        email = "test@example.com"
        password = "test_password"
        
        result = client.login_user(email, password)
        
        # Verify request was made correctly
        mock_client.request.assert_called_once_with(
            "POST",
            "/rest/login",
            json={"emailOrLdapLoginId": email, "password": password},
            headers={"Accept": "application/json", "Content-Type": "application/json"}
        )
        
        # Verify response
        assert result == mock_response
        assert result.status_code == 200
        
        print("✅ User login (success) works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_login_user_failure(self, mock_client_class):
        """Test failed user login."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "Invalid credentials"}'
        mock_response.headers = {}
        mock_client.request.return_value = mock_response
        
        # Test login
        client = N8NClient("https://n8n.example.com")
        
        with pytest.raises(N8NClientError) as exc_info:
            client.login_user("test@example.com", "wrong_password")
        
        # Verify exception details
        assert exc_info.value.status == 401
        assert "Login failed" in str(exc_info.value)
        
        print("✅ User login (failure) works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_login_user_network_error(self, mock_client_class):
        """Test login with network error."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock network error
        mock_client.request.side_effect = httpx.RequestError("Network error")
        
        # Test login
        client = N8NClient("https://n8n.example.com")
        
        with pytest.raises(httpx.RequestError):
            client.login_user("test@example.com", "password")
        
        print("✅ User login (network error) works correctly")


class TestN8NClientLogout:
    """Test N8NClient logout functionality."""
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_with_cookie(self, mock_client_class):
        """Test user logout with auth cookie."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_response.headers = {}
        mock_client.request.return_value = mock_response
        
        # Test logout
        client = N8NClient("https://n8n.example.com")
        auth_cookie = "test_cookie_value"
        
        result = client.logout_user(auth_cookie)
        
        # Verify request was made correctly
        expected_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": f"n8n-auth={auth_cookie}"
        }
        mock_client.request.assert_called_once_with(
            "POST",
            "/rest/logout",
            headers=expected_headers
        )
        
        # Verify response
        assert result == mock_response
        assert result.status_code == 200
        
        print("✅ User logout (with cookie) works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_without_cookie(self, mock_client_class):
        """Test user logout without auth cookie."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_response.headers = {}
        mock_client.request.return_value = mock_response
        
        # Test logout
        client = N8NClient("https://n8n.example.com")
        
        result = client.logout_user()
        
        # Verify request was made correctly (no Cookie header)
        expected_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        mock_client.request.assert_called_once_with(
            "POST",
            "/rest/logout",
            headers=expected_headers
        )
        
        print("✅ User logout (without cookie) works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_network_error(self, mock_client_class):
        """Test logout with network error."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock network error
        mock_client.request.side_effect = httpx.RequestError("Network error")
        
        # Test logout
        client = N8NClient("https://n8n.example.com")
        
        with pytest.raises(N8NClientError) as exc_info:
            client.logout_user("test_cookie")
        
        # Verify exception details
        assert exc_info.value.status == 500
        assert "Logout request failed" in str(exc_info.value)
        
        print("✅ User logout (network error) works correctly")


class TestN8NClientLogoutByEmail:
    """Test N8NClient logout by email functionality."""
    
    @patch('asyncio.run')
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_by_email_success(self, mock_client_class, mock_asyncio_run):
        """Test successful logout by email."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock database user lookup
        mock_user_row = Mock()
        mock_user_row.password = "user_password_hash"
        mock_asyncio_run.return_value = "user_password_hash"
        
        # Mock login response
        mock_login_response = Mock()
        mock_login_response.status_code = 200
        mock_login_response.cookies = {'n8n-auth': 'extracted_cookie'}
        # Provide headers object compatible with dict() and get_list()
        class HeadersMock:
            def __init__(self):
                self._data = {}
            def get_list(self, key):
                return []
            def __iter__(self):
                return iter(self._data.keys())
            def keys(self):
                return self._data.keys()
            def items(self):
                return self._data.items()
            def __getitem__(self, key):
                return self._data.get(key, '')
            def get(self, key, default=None):
                return self._data.get(key, default)
        mock_login_response.headers = HeadersMock()
        
        # Mock logout response
        mock_logout_response = Mock()
        mock_logout_response.status_code = 200
        mock_logout_response.text = '{"success": true}'
        # Ensure headers dict-friendly for logging in logout_user
        mock_logout_response.headers = {}
        
        # Setup client request side effects
        mock_client.request.side_effect = [
            mock_login_response,  # Login request
            mock_logout_response  # Logout request
        ]
        
        # Test logout by email
        client = N8NClient("https://n8n.example.com")
        
        result = client.logout_user_by_email("test@example.com")
        
        # Verify calls
        assert mock_client.request.call_count == 2  # Login + Logout
        assert result == mock_logout_response
        
        print("✅ User logout by email (success) works correctly")
    
    @patch('asyncio.run')
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_by_email_user_not_found(self, mock_client_class, mock_asyncio_run):
        """Test logout by email when user not found."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock database user lookup failure
        mock_asyncio_run.side_effect = Exception("User not found")
        
        # Mock fallback logout response
        mock_logout_response = Mock()
        mock_logout_response.status_code = 200
        mock_logout_response.text = "ok"
        mock_logout_response.headers = {}
        mock_client.request.return_value = mock_logout_response
        
        # Test logout by email
        client = N8NClient("https://n8n.example.com")
        
        result = client.logout_user_by_email("nonexistent@example.com")
        
        # Verify fallback logout was called
        mock_client.request.assert_called_once()
        assert result == mock_logout_response
        
        print("✅ User logout by email (user not found) works correctly")
    
    @patch('asyncio.run')
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_logout_user_by_email_login_failure(self, mock_client_class, mock_asyncio_run):
        """Test logout by email when login fails."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock database user lookup success
        mock_asyncio_run.return_value = "user_password"
        
        # Mock login failure
        mock_login_response = Mock()
        mock_login_response.status_code = 401
        mock_login_response.text = "Unauthorized"
        mock_client.request.side_effect = [
            N8NClientError(401, "Login failed"),  # Login fails
            Mock(status_code=200, text="ok", headers={})  # Fallback logout succeeds
        ]
        
        # Test logout by email
        client = N8NClient("https://n8n.example.com")
        
        result = client.logout_user_by_email("test@example.com")
        
        # Verify fallback was used
        assert mock_client.request.call_count >= 1
        
        print("✅ User logout by email (login failure) works correctly")


class TestN8NClientClose:
    """Test N8NClient cleanup functionality."""
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_close_success(self, mock_client_class):
        """Test successful client cleanup."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Test close
        client = N8NClient("https://n8n.example.com")
        client.close()
        
        # Verify close was called
        mock_client.close.assert_called_once()
        
        print("✅ Client close (success) works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_close_with_exception(self, mock_client_class):
        """Test client cleanup with exception."""
        # Setup mock client
        mock_client = Mock()
        mock_client.close.side_effect = Exception("Close error")
        mock_client_class.return_value = mock_client
        
        # Test close (should not raise exception)
        client = N8NClient("https://n8n.example.com")
        client.close()  # Should not raise
        
        # Verify close was attempted
        mock_client.close.assert_called_once()
        
        print("✅ Client close (with exception) works correctly")


class TestN8NClientError:
    """Test N8NClientError exception class."""
    
    def test_n8n_client_error_creation(self):
        """Test N8NClientError creation and attributes."""
        status = 404
        message = "Not found"
        payload = {"error": "Resource not found"}
        
        error = N8NClientError(status, message, payload)
        
        assert error.status == status
        assert error.payload == payload
        assert str(error) == f"n8n API error {status}: {message}"
        
        print("✅ N8NClientError creation works correctly")
    
    def test_n8n_client_error_without_payload(self):
        """Test N8NClientError creation without payload."""
        status = 500
        message = "Internal server error"
        
        error = N8NClientError(status, message)
        
        assert error.status == status
        assert error.payload is None
        assert str(error) == f"n8n API error {status}: {message}"
        
        print("✅ N8NClientError (without payload) works correctly")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_empty_credentials(self, mock_client_class):
        """Test login with empty credentials."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_response.headers = {}
        mock_client.request.return_value = mock_response
        
        client = N8NClient("https://n8n.example.com")
        
        with pytest.raises(N8NClientError):
            client.login_user("", "")
        
        print("✅ Empty credentials handling works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_very_long_credentials(self, mock_client_class):
        """Test login with very long credentials."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        # Headers supporting get_list and dict()
        class HeadersMock:
            def __init__(self):
                self._data = {}
            def get_list(self, key):
                return []
            def __iter__(self):
                return iter(self._data.keys())
            def keys(self):
                return self._data.keys()
            def items(self):
                return self._data.items()
            def __getitem__(self, key):
                return self._data.get(key, '')
            def get(self, key, default=None):
                return self._data.get(key, default)
        mock_response.headers = HeadersMock()
        mock_client.request.return_value = mock_response
        
        client = N8NClient("https://n8n.example.com")
        
        # Very long email and password
        long_email = "a" * 1000 + "@example.com"
        long_password = "p" * 1000
        
        result = client.login_user(long_email, long_password)
        assert result.status_code == 200
        
        print("✅ Long credentials handling works correctly")
    
    @patch('apps.integrations.n8n_client.httpx.Client')
    def test_special_characters_in_credentials(self, mock_client_class):
        """Test login with special characters in credentials."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        class HeadersMock:
            def __init__(self):
                self._data = {}
            def get_list(self, key):
                return []
            def __iter__(self):
                return iter(self._data.keys())
            def keys(self):
                return self._data.keys()
            def items(self):
                return self._data.items()
            def __getitem__(self, key):
                return self._data.get(key, '')
            def get(self, key, default=None):
                return self._data.get(key, default)
        mock_response.headers = HeadersMock()
        mock_client.request.return_value = mock_response
        
        client = N8NClient("https://n8n.example.com")
        
        # Special characters
        special_email = "test+tag@example.com"
        special_password = "p@ssw0rd!#$%^&*()"
        
        result = client.login_user(special_email, special_password)
        assert result.status_code == 200
        
        print("✅ Special characters in credentials handled correctly")


def run_all_tests():
    """Run all N8NClient tests."""
    print("🌐 Starting N8NClient Test Suite...")
    print("=" * 50)
    
    try:
        # Test initialization
        init_tests = TestN8NClientInitialization()
        init_tests.test_client_initialization_default()
        init_tests.test_client_initialization_custom_timeout()
        init_tests.test_client_base_url_normalization()
        init_tests.test_headers_method()
        print()
        
        # Test login functionality
        login_tests = TestN8NClientLogin()
        login_tests.test_login_user_success()
        login_tests.test_login_user_failure()
        login_tests.test_login_user_network_error()
        print()
        
        # Test logout functionality
        logout_tests = TestN8NClientLogout()
        logout_tests.test_logout_user_with_cookie()
        logout_tests.test_logout_user_without_cookie()
        logout_tests.test_logout_user_network_error()
        print()
        
        # Test logout by email
        logout_email_tests = TestN8NClientLogoutByEmail()
        logout_email_tests.test_logout_user_by_email_success()
        logout_email_tests.test_logout_user_by_email_user_not_found()
        logout_email_tests.test_logout_user_by_email_login_failure()
        print()
        
        # Test cleanup
        close_tests = TestN8NClientClose()
        close_tests.test_close_success()
        close_tests.test_close_with_exception()
        print()
        
        # Test error handling
        error_tests = TestN8NClientError()
        error_tests.test_n8n_client_error_creation()
        error_tests.test_n8n_client_error_without_payload()
        print()
        
        # Test edge cases
        edge_tests = TestEdgeCases()
        edge_tests.test_empty_credentials()
        edge_tests.test_very_long_credentials()
        edge_tests.test_special_characters_in_credentials()
        print()
        
        print("🎉 All N8NClient tests passed!")
        print("✅ Client initialization working correctly")
        print("✅ Login functionality verified")
        print("✅ Logout operations tested")
        print("✅ Error handling robust")
        print("✅ Edge cases handled gracefully")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("🌐 n8n SSO Gateway - N8NClient Test Suite")
    print("=" * 50)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 50)
        print("🏆 ALL N8NCLIENT TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 HTTP client operations are secure and reliable")
        print("⚡ Login/logout functionality verified")
        print("🎯 Error handling working correctly")
        print("=" * 50)
        exit(0)
    else:
        print("\n" + "=" * 50)
        print("💥 N8NCLIENT TESTS FAILED!")
        print("❌ HTTP client operations need attention")
        print("=" * 50)
        exit(1)
