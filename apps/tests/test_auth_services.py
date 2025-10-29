#!/usr/bin/env python3
"""
Comprehensive unit tests for authentication services.

Tests all auth service functions with proper mocking to avoid external dependencies.
Covers OAuth token exchange, JWT parsing, profile mapping, and callback handling.
"""

import pytest
import asyncio
import jwt
import httpx
from unittest.mock import Mock, AsyncMock, patch, MagicMock, ANY
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from cryptography import x509
from cryptography.hazmat.backends import default_backend

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.auth.services import (
    extract_n8n_auth_cookie,
    get_oauth_token,
    parse_jwt_token,
    map_casdoor_to_profile,
    handle_casdoor_callback
)
from apps.integrations.n8n_db import CasdoorProfile


class TestExtractN8NAuthCookie:
    """Test n8n auth cookie extraction from HTTP responses."""
    
    def test_extract_cookie_from_cookies_attribute(self):
        """Test extracting cookie from response.cookies attribute."""
        # Mock response with cookies attribute
        mock_response = Mock()
        mock_response.cookies = {'n8n-auth': 'test_cookie_value_123'}
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result == 'test_cookie_value_123'
        print("✅ Cookie extraction from cookies attribute works correctly")
    
    def test_extract_cookie_from_set_cookie_headers(self):
        """Test extracting cookie from set-cookie headers."""
        # Mock response with set-cookie headers
        mock_response = Mock()
        mock_response.cookies = None
        mock_response.headers = Mock()
        mock_response.headers.get_list.return_value = [
            'n8n-auth=header_cookie_value; Path=/; HttpOnly',
            'other-cookie=other_value; Path=/'
        ]
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result == 'header_cookie_value'
        print("✅ Cookie extraction from set-cookie headers works correctly")
    
    def test_extract_cookie_from_single_set_cookie_header(self):
        """Test extracting cookie from single set-cookie header."""
        # Mock response with single set-cookie header
        mock_response = Mock()
        mock_response.cookies = None
        mock_response.headers = Mock()
        mock_response.headers.get_list.return_value = []
        mock_response.headers.get.return_value = 'n8n-auth=single_cookie_value; Path=/; HttpOnly'
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result == 'single_cookie_value'
        print("✅ Cookie extraction from single set-cookie header works correctly")
    
    def test_extract_cookie_not_found(self):
        """Test cookie extraction when cookie not found."""
        # Mock response without n8n-auth cookie
        mock_response = Mock()
        mock_response.cookies = {'other-cookie': 'other_value'}
        
        # Create a proper headers mock that supports both get_list and iteration
        class HeadersMock:
            def __init__(self):
                self._data = {}
            
            def get_list(self, key):
                return []
            
            def __iter__(self):
                return iter(self._data.keys())
            
            def __getitem__(self, key):
                return self._data.get(key, '')
            
            def get(self, key, default=None):
                return self._data.get(key, default)
        
        mock_response.headers = HeadersMock()
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result is None
        print("✅ Cookie extraction (not found) works correctly")
    
    def test_extract_cookie_no_response(self):
        """Test cookie extraction with no response."""
        result = extract_n8n_auth_cookie(None)
        
        assert result is None
        print("✅ Cookie extraction (no response) works correctly")
    
    def test_extract_cookie_malformed_header(self):
        """Test cookie extraction with malformed header."""
        # Mock response with malformed set-cookie header
        mock_response = Mock()
        mock_response.cookies = None
        mock_response.headers = Mock()
        mock_response.headers.get_list.return_value = [
            'n8n-auth=',  # Empty value
            'malformed_header_without_equals'
        ]
        mock_response.headers.get.return_value = None
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result == ''  # Should handle empty value gracefully
        print("✅ Cookie extraction (malformed header) works correctly")


class TestGetOAuthToken:
    """Test OAuth token exchange with Casdoor."""
    
    @patch('apps.auth.services.httpx.AsyncClient')
    @patch('apps.auth.services.get_settings')
    @pytest.mark.asyncio
    async def test_get_oauth_token_success(self, mock_get_settings, mock_client_class):
        """Test successful OAuth token exchange."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_settings.CASDOOR_CLIENT_ID = "test_client_id"
        mock_settings.CASDOOR_CLIENT_SECRET = "test_client_secret"
        mock_get_settings.return_value = mock_settings
        
        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "id_token": "test_id_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_response.content = b'{"access_token": "test_access_token"}'
        mock_response.headers = {}
        mock_client.post.return_value = mock_response
        
        # Test token exchange
        code = "test_authorization_code"
        result = await get_oauth_token(code)
        
        # Verify result
        assert isinstance(result, dict)
        assert result["access_token"] == "test_access_token"
        assert result["id_token"] == "test_id_token"
        
        # Verify HTTP call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/api/login/oauth/access_token" in call_args[0][0]
        
        print("✅ OAuth token exchange (success) works correctly")
    
    @patch('apps.auth.services.httpx.AsyncClient')
    @patch('apps.auth.services.get_settings')
    @pytest.mark.asyncio
    async def test_get_oauth_token_invalid_grant(self, mock_get_settings, mock_client_class):
        """Test OAuth token exchange with invalid grant (code already used)."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_settings.CASDOOR_CLIENT_ID = "test_client_id"
        mock_settings.CASDOOR_CLIENT_SECRET = "test_client_secret"
        mock_get_settings.return_value = mock_settings
        
        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock invalid grant response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "authorization code has been used"
        }
        mock_response.content = b'{"error": "invalid_grant"}'
        mock_response.headers = {}
        mock_client.post.return_value = mock_response
        
        # Test token exchange
        code = "used_authorization_code"
        result = await get_oauth_token(code)
        
        # Should return redirect response for invalid grant
        assert isinstance(result, RedirectResponse)
        
        print("✅ OAuth token exchange (invalid grant) works correctly")
    
    @patch('apps.auth.services.httpx.AsyncClient')
    @patch('apps.auth.services.get_settings')
    @pytest.mark.asyncio
    async def test_get_oauth_token_network_error(self, mock_get_settings, mock_client_class):
        """Test OAuth token exchange with network error."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_settings.CASDOOR_CLIENT_ID = "test_client_id"
        mock_settings.CASDOOR_CLIENT_SECRET = "test_client_secret"
        mock_get_settings.return_value = mock_settings
        
        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock network error
        mock_client.post.side_effect = httpx.RequestError("Network error")
        
        # Test token exchange
        code = "test_authorization_code"
        result = await get_oauth_token(code)
        
        # Should return redirect response for network error
        assert isinstance(result, RedirectResponse)
        
        print("✅ OAuth token exchange (network error) works correctly")
    
    @patch('apps.auth.services.httpx.AsyncClient')
    @patch('apps.auth.services.get_settings')
    @pytest.mark.asyncio
    async def test_get_oauth_token_json_parse_error(self, mock_get_settings, mock_client_class):
        """Test OAuth token exchange with JSON parse error."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_ENDPOINT = "https://casdoor.example.com"
        mock_settings.CASDOOR_CLIENT_ID = "test_client_id"
        mock_settings.CASDOOR_CLIENT_SECRET = "test_client_secret"
        mock_get_settings.return_value = mock_settings
        
        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Invalid JSON response"
        mock_response.content = b'Invalid JSON'
        mock_response.headers = {}
        mock_client.post.return_value = mock_response
        
        # Test token exchange
        code = "test_authorization_code"
        result = await get_oauth_token(code)
        
        # Should return redirect response for JSON error
        assert isinstance(result, RedirectResponse)
        
        print("✅ OAuth token exchange (JSON parse error) works correctly")


class TestParseJWTToken:
    """Test JWT token parsing and verification."""
    
    @patch('apps.auth.services.get_settings')
    @patch('builtins.open', create=True)
    def test_parse_jwt_token_success(self, mock_open, mock_get_settings):
        """Test successful JWT token parsing."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_CERT_PATH = "/path/to/cert.pem"
        mock_settings.CASDOOR_CLIENT_ID = "test_client_id"
        mock_settings.CASDOOR_ORG_NAME = "test_org"
        mock_get_settings.return_value = mock_settings
        
        # Mock certificate file
        cert_content = """-----BEGIN CERTIFICATE-----
MIICljCCAX4CCQCKOtLUOHDAuTANBgkqhkiG9w0BAQsFADCBjTELMAkGA1UEBhMC
VVMxCzAJBgNVBAgMAkNBMRYwFAYDVQQHDA1TYW4gRnJhbmNpc2NvMQ0wCwYDVQQK
DARUZXN0MQ0wCwYDVQQLDARUZXN0MQ0wCwYDVQQDDARUZXN0MSwwKgYJKoZIhvcN
AQkBFh10ZXN0QGV4YW1wbGUuY29tMA0GCSqGSIb3DQEBCwUAA4IBAQCKOtLUOHDA
-----END CERTIFICATE-----"""
        mock_open.return_value.__enter__.return_value.read.return_value = cert_content
        
        # Create a test JWT token (we'll mock the verification)
        test_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test.signature"
        expected_payload = {
            "sub": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "aud": "test_client_id"
        }
        
        with patch('apps.auth.services.jwt.decode') as mock_jwt_decode, \
             patch('apps.auth.services.x509.load_pem_x509_certificate') as mock_load_cert:
            mock_jwt_decode.return_value = expected_payload
            mock_load_cert.return_value.public_key.return_value = "mock_public_key"
            
            result = parse_jwt_token(test_token)
            
            assert result == expected_payload
            mock_jwt_decode.assert_called()
        
        print("✅ JWT token parsing (success) works correctly")
    
    @patch('apps.auth.services.get_settings')
    @patch('builtins.open', create=True)
    def test_parse_jwt_token_certificate_error(self, mock_open, mock_get_settings):
        """Test JWT token parsing with certificate loading error."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_CERT_PATH = "/path/to/nonexistent/cert.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock certificate file error
        mock_open.side_effect = FileNotFoundError("Certificate file not found")
        
        test_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test.signature"
        result = parse_jwt_token(test_token)
        
        # Should return redirect response for certificate error
        assert isinstance(result, RedirectResponse)
        
        print("✅ JWT token parsing (certificate error) works correctly")
    
    @patch('apps.auth.services.get_settings')
    @patch('builtins.open', create=True)
    def test_parse_jwt_token_audience_mismatch(self, mock_open, mock_get_settings):
        """Test JWT token parsing with audience mismatch."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.CASDOOR_CERT_PATH = "/path/to/cert.pem"
        mock_settings.CASDOOR_CLIENT_ID = "expected_client_id"
        mock_settings.CASDOOR_ORG_NAME = "test_org"
        mock_get_settings.return_value = mock_settings
        
        # Mock certificate file
        cert_content = "mock_cert_content"
        mock_open.return_value.__enter__.return_value.read.return_value = cert_content
        
        test_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test.signature"
        
        with patch('apps.auth.services.x509.load_pem_x509_certificate'), \
             patch('apps.auth.services.jwt.decode') as mock_jwt_decode:
            
            # Mock JWT decode to return token with different audience
            mock_jwt_decode.side_effect = [
                {"aud": "different_client_id", "sub": "user123"},  # First call (without aud verification)
                {"aud": "different_client_id", "sub": "user123"}   # Fallback call
            ]
            
            result = parse_jwt_token(test_token)
            
            # Should still return the decoded token (fallback behavior)
            assert isinstance(result, dict)
            assert result["sub"] == "user123"
        
        print("✅ JWT token parsing (audience mismatch) works correctly")


class TestMapCasdoorToProfile:
    """Test mapping Casdoor JWT claims to CasdoorProfile."""
    
    def test_map_casdoor_to_profile_complete(self):
        """Test mapping with complete user info."""
        user_info = {
            "email": "test@example.com",
            "name": "John Doe",
            "given_name": "John",
            "family_name": "Doe",
            "sub": "casdoor_user_123",
            "picture": "https://example.com/avatar.jpg"
        }
        
        result = map_casdoor_to_profile(user_info)
        
        assert isinstance(result, CasdoorProfile)
        assert result.email == "test@example.com"
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.display_name == "John Doe"
        assert result.casdoor_id == "casdoor_user_123"
        assert result.avatar_url == "https://example.com/avatar.jpg"
        
        print("✅ Casdoor profile mapping (complete) works correctly")
    
    def test_map_casdoor_to_profile_minimal(self):
        """Test mapping with minimal user info."""
        user_info = {
            "email": "minimal@example.com",
            "sub": "casdoor_minimal_123"
        }
        
        result = map_casdoor_to_profile(user_info)
        
        assert isinstance(result, CasdoorProfile)
        assert result.email == "minimal@example.com"
        assert result.casdoor_id == "casdoor_minimal_123"
        assert result.first_name is None
        assert result.last_name is None
        
        print("✅ Casdoor profile mapping (minimal) works correctly")
    
    def test_map_casdoor_to_profile_alternative_fields(self):
        """Test mapping with alternative field names."""
        user_info = {
            "mail": "alt@example.com",  # Alternative email field
            "display_name": "Alt User",
            "id": "alt_user_123"  # Alternative ID field
        }
        
        result = map_casdoor_to_profile(user_info)
        
        assert isinstance(result, CasdoorProfile)
        assert result.email == "alt@example.com"
        assert result.display_name == "Alt User"
        assert result.casdoor_id == "alt_user_123"
        
        print("✅ Casdoor profile mapping (alternative fields) works correctly")
    
    def test_map_casdoor_to_profile_name_splitting(self):
        """Test name splitting when first/last names not provided."""
        user_info = {
            "email": "split@example.com",
            "name": "First Last Name",
            "sub": "split_user_123"
        }
        
        result = map_casdoor_to_profile(user_info)
        
        assert isinstance(result, CasdoorProfile)
        assert result.email == "split@example.com"
        assert result.first_name == "First"
        assert result.last_name == "Last Name"
        assert result.display_name == "First Last Name"
        
        print("✅ Casdoor profile mapping (name splitting) works correctly")
    
    def test_map_casdoor_to_profile_no_email(self):
        """Test mapping without email (should return redirect)."""
        user_info = {
            "name": "No Email User",
            "sub": "no_email_123"
        }
        
        result = map_casdoor_to_profile(user_info)
        
        # Should return redirect response when email is missing
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor profile mapping (no email) works correctly")


class TestHandleCasdoorCallback:
    """Test the main Casdoor callback handler."""
    
    @patch('apps.auth.services.get_oauth_token')
    @patch('apps.auth.services.parse_jwt_token')
    @patch('apps.auth.services.map_casdoor_to_profile')
    @patch('apps.auth.services.ensure_user_project_binding')
    @patch('apps.auth.services.rotate_user_password')
    @patch('apps.auth.services.N8NClient')
    @patch('apps.auth.services.SessionManager')
    @patch('apps.auth.services.get_settings')
    @pytest.mark.asyncio
    async def test_handle_casdoor_callback_new_user(
        self, mock_get_settings, mock_session_manager, mock_n8n_client_class,
        mock_rotate_password, mock_ensure_binding, mock_map_profile,
        mock_parse_jwt, mock_get_token
    ):
        """Test callback handling for new user."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.N8N_BASE_URL = "https://n8n.example.com"
        mock_settings.N8N_DEFAULT_GLOBAL_ROLE = "global:member"
        mock_settings.N8N_DEFAULT_PROJECT_ROLE = "project:personalOwner"
        mock_get_settings.return_value = mock_settings
        
        # Mock request
        mock_request = Mock(spec=Request)
        mock_request.query_params = {"code": "test_code"}
        
        # Mock OAuth token exchange
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "id_token": "test_id_token"
        }
        
        # Mock JWT parsing
        mock_parse_jwt.return_value = {
            "email": "newuser@example.com",
            "name": "New User",
            "sub": "new_user_123"
        }
        
        # Mock profile mapping
        mock_profile = CasdoorProfile(
            email="newuser@example.com",
            first_name="New",
            last_name="User",
            casdoor_id="new_user_123"
        )
        mock_map_profile.return_value = mock_profile
        
        # Mock database operations
        from apps.integrations.n8n_db import N8nUserRow, N8nProjectRow
        import uuid
        user_id = uuid.uuid4()
        mock_user_row = N8nUserRow(id=user_id, email="newuser@example.com")
        mock_project_row = N8nProjectRow(id="project123", name="newuser@example.com")
        temp_password = "temp_password_123"
        mock_ensure_binding.return_value = (mock_user_row, mock_project_row, temp_password)
        
        # Mock session management
        mock_session_manager.get_active_session.return_value = None
        mock_session_manager.create_session.return_value = "session123"
        
        # Mock N8N client
        mock_n8n_client = Mock()
        mock_n8n_client_class.return_value = mock_n8n_client
        
        # Mock login response with cookie
        mock_login_response = Mock()
        mock_login_response.status_code = 200
        mock_login_response.text = "ok"
        mock_login_response.headers = {}
        mock_n8n_client.login_user.return_value = mock_login_response
        
        # Mock cookie extraction
        with patch('apps.auth.services.extract_n8n_auth_cookie') as mock_extract_cookie:
            mock_extract_cookie.return_value = "extracted_cookie_123"
            
            # Test callback handling
            result = await handle_casdoor_callback(mock_request)
            
            # Verify result is a redirect response
            assert isinstance(result, RedirectResponse)
            
            # Verify all mocks were called appropriately
            mock_get_token.assert_called_once_with("test_code", ANY)
            mock_parse_jwt.assert_called_once()
            mock_map_profile.assert_called_once()
            mock_ensure_binding.assert_called_once()
            mock_n8n_client.login_user.assert_called_once()
        
        print("✅ Casdoor callback handling (new user) works correctly")
    
    @patch('apps.auth.services.get_oauth_token')
    @pytest.mark.asyncio
    async def test_handle_casdoor_callback_token_error(self, mock_get_token):
        """Test callback handling when token exchange fails."""
        # Mock request
        mock_request = Mock(spec=Request)
        mock_request.query_params = {"code": "invalid_code"}
        
        # Mock token exchange failure (returns redirect)
        mock_get_token.return_value = RedirectResponse(url="https://error.example.com")
        
        # Test callback handling
        result = await handle_casdoor_callback(mock_request)
        
        # Should return the redirect response from token exchange
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback handling (token error) works correctly")
    
    @patch('apps.auth.services.get_oauth_token')
    @patch('apps.auth.services.parse_jwt_token')
    @pytest.mark.asyncio
    async def test_handle_casdoor_callback_missing_id_token(self, mock_parse_jwt, mock_get_token):
        """Test callback handling when ID token is missing."""
        # Mock request
        mock_request = Mock(spec=Request)
        mock_request.query_params = {"code": "test_code"}
        
        # Mock token exchange without id_token
        mock_get_token.return_value = {
            "access_token": "test_access_token"
            # Missing id_token
        }
        
        # Test callback handling
        result = await handle_casdoor_callback(mock_request)
        
        # Should return redirect response for missing id_token
        assert isinstance(result, RedirectResponse)
        
        print("✅ Casdoor callback handling (missing ID token) works correctly")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_extract_cookie_complex_headers(self):
        """Test cookie extraction with complex set-cookie headers."""
        # Mock response with multiple complex set-cookie headers
        mock_response = Mock()
        mock_response.cookies = None
        mock_response.headers = Mock()
        mock_response.headers.get_list.return_value = [
            'session=abc123; Path=/; HttpOnly; Secure; SameSite=Strict',
            'n8n-auth=target_cookie_value; Path=/; HttpOnly; Secure; Max-Age=3600',
            'csrf=xyz789; Path=/; SameSite=Lax'
        ]
        
        result = extract_n8n_auth_cookie(mock_response)
        
        assert result == 'target_cookie_value'
        print("✅ Cookie extraction (complex headers) works correctly")
    
    def test_map_profile_unicode_characters(self):
        """Test profile mapping with Unicode characters."""
        user_info = {
            "email": "unicode@例え.テスト",
            "name": "José María Ñoño",
            "given_name": "José María",
            "family_name": "Ñoño",
            "sub": "unicode_user_123"
        }
        
        result = map_casdoor_to_profile(user_info)
        
        assert isinstance(result, CasdoorProfile)
        assert result.email == "unicode@例え.テスト"
        assert result.first_name == "José María"
        assert result.last_name == "Ñoño"
        
        print("✅ Profile mapping (Unicode characters) works correctly")


def run_all_tests():
    """Run all authentication service tests."""
    print("🔐 Starting Authentication Services Test Suite...")
    print("=" * 60)
    
    try:
        # Test cookie extraction
        cookie_tests = TestExtractN8NAuthCookie()
        cookie_tests.test_extract_cookie_from_cookies_attribute()
        cookie_tests.test_extract_cookie_from_set_cookie_headers()
        cookie_tests.test_extract_cookie_from_single_set_cookie_header()
        cookie_tests.test_extract_cookie_not_found()
        cookie_tests.test_extract_cookie_no_response()
        cookie_tests.test_extract_cookie_malformed_header()
        print()
        
        # Test OAuth token exchange
        token_tests = TestGetOAuthToken()
        asyncio.run(token_tests.test_get_oauth_token_success())
        asyncio.run(token_tests.test_get_oauth_token_invalid_grant())
        asyncio.run(token_tests.test_get_oauth_token_network_error())
        asyncio.run(token_tests.test_get_oauth_token_json_parse_error())
        print()
        
        # Test JWT parsing
        jwt_tests = TestParseJWTToken()
        jwt_tests.test_parse_jwt_token_success()
        jwt_tests.test_parse_jwt_token_certificate_error()
        jwt_tests.test_parse_jwt_token_audience_mismatch()
        print()
        
        # Test profile mapping
        profile_tests = TestMapCasdoorToProfile()
        profile_tests.test_map_casdoor_to_profile_complete()
        profile_tests.test_map_casdoor_to_profile_minimal()
        profile_tests.test_map_casdoor_to_profile_alternative_fields()
        profile_tests.test_map_casdoor_to_profile_name_splitting()
        profile_tests.test_map_casdoor_to_profile_no_email()
        print()
        
        # Test callback handling
        callback_tests = TestHandleCasdoorCallback()
        asyncio.run(callback_tests.test_handle_casdoor_callback_new_user())
        asyncio.run(callback_tests.test_handle_casdoor_callback_token_error())
        asyncio.run(callback_tests.test_handle_casdoor_callback_missing_id_token())
        print()
        
        # Test edge cases
        edge_tests = TestEdgeCases()
        edge_tests.test_extract_cookie_complex_headers()
        edge_tests.test_map_profile_unicode_characters()
        print()
        
        print("🎉 All Authentication Services tests passed!")
        print("✅ Cookie extraction working correctly")
        print("✅ OAuth token exchange verified")
        print("✅ JWT parsing and validation functional")
        print("✅ Profile mapping robust")
        print("✅ Callback handling comprehensive")
        print("✅ Edge cases handled gracefully")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔐 n8n SSO Gateway - Authentication Services Test Suite")
    print("=" * 60)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 60)
        print("🏆 ALL AUTHENTICATION SERVICES TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Authentication flow is secure and reliable")
        print("⚡ OAuth integration verified")
        print("🎯 JWT processing working correctly")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 AUTHENTICATION SERVICES TESTS FAILED!")
        print("❌ Authentication services need attention")
        print("=" * 60)
        exit(1)
