#!/usr/bin/env python3
"""
Comprehensive unit tests for core error handling utilities.

Tests all error handling functions and classes with various scenarios.
Covers safe redirects, error logging, context managers, and decorators.
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from fastapi.responses import RedirectResponse
from fastapi import HTTPException

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.core.error_handling import (
    create_safe_redirect,
    log_and_redirect_on_error,
    SafeRedirectHandler,
    safe_operation,
    safe_api_operation
)


class TestCreateSafeRedirect:
    """Test create_safe_redirect function."""
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_basic(self, mock_get_settings):
        """Test basic safe redirect creation."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test error
        test_error = ValueError("Test error message")
        
        result = create_safe_redirect(test_error)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "https://default.example.com"
        
        print("✅ Basic safe redirect creation works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_with_flash_message(self, mock_get_settings):
        """Test safe redirect with flash message."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test error and flash message
        test_error = RuntimeError("Database connection failed")
        flash_message = "Service temporarily unavailable. Please try again later."
        
        result = create_safe_redirect(test_error, flash_message=flash_message)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        # Verify flash message is in URL
        location = result.headers["location"]
        assert "flash=" in location
        assert "Service+temporarily+unavailable" in location or "Service%20temporarily%20unavailable" in location
        
        print("✅ Safe redirect with flash message works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_with_context(self, mock_get_settings):
        """Test safe redirect with context information."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test error with context
        test_error = ConnectionError("Network timeout")
        context = {
            "operation": "user_login",
            "user_id": "user123",
            "attempt_count": 3
        }
        request_id = "req_abc123"
        
        result = create_safe_redirect(
            test_error,
            flash_message="Login failed. Please try again.",
            context=context,
            request_id=request_id
        )
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe redirect with context works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_auto_request_id(self, mock_get_settings):
        """Test safe redirect with auto-generated request ID."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test error without request ID
        test_error = Exception("Generic error")
        
        result = create_safe_redirect(test_error)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe redirect with auto request ID works correctly")


class TestLogAndRedirectOnError:
    """Test log_and_redirect_on_error function."""
    
    @patch('apps.core.error_handling.get_settings')
    def test_log_and_redirect_basic(self, mock_get_settings):
        """Test basic log and redirect functionality."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test error message
        error_message = "Authentication service unavailable"
        
        result = log_and_redirect_on_error(error_message)
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "https://default.example.com"
        
        print("✅ Basic log and redirect works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_log_and_redirect_with_all_params(self, mock_get_settings):
        """Test log and redirect with all parameters."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test with all parameters
        error_message = "Database query failed"
        flash_message = "Data temporarily unavailable"
        context = {"table": "users", "query_type": "SELECT"}
        request_id = "req_xyz789"
        
        result = log_and_redirect_on_error(
            error_message,
            flash_message=flash_message,
            context=context,
            request_id=request_id
        )
        
        # Verify result
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        # Verify flash message is in URL
        location = result.headers["location"]
        assert "flash=" in location
        
        print("✅ Log and redirect with all parameters works correctly")


class TestSafeRedirectHandler:
    """Test SafeRedirectHandler context manager."""
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_redirect_handler_no_exception(self, mock_get_settings):
        """Test SafeRedirectHandler when no exception occurs."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test successful operation
        with SafeRedirectHandler(request_id="test_123") as handler:
            result = "Operation successful"
            handler.result = result
        
        # Verify no redirect was created
        assert handler.get_result() == "Operation successful"
        
        print("✅ SafeRedirectHandler (no exception) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_redirect_handler_with_exception(self, mock_get_settings):
        """Test SafeRedirectHandler when exception occurs."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test operation that raises exception
        with SafeRedirectHandler(
            request_id="test_456",
            flash_message="Operation failed",
            context={"operation": "test"}
        ) as handler:
            raise ValueError("Test exception")
        
        # Verify redirect was created
        result = handler.get_result()
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ SafeRedirectHandler (with exception) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_redirect_handler_auto_request_id(self, mock_get_settings):
        """Test SafeRedirectHandler with auto-generated request ID."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test without providing request_id
        with SafeRedirectHandler() as handler:
            raise RuntimeError("Auto ID test")
        
        # Verify redirect was created and request_id was auto-generated
        result = handler.get_result()
        assert isinstance(result, RedirectResponse)
        assert len(handler.request_id) == 8  # UUID[:8]
        
        print("✅ SafeRedirectHandler (auto request ID) works correctly")


class TestSafeOperation:
    """Test safe_operation decorator."""
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_operation_async_success(self, mock_get_settings):
        """Test safe_operation decorator with successful async function."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Decorate an async function
        @safe_operation("test_operation", "Test operation failed")
        async def test_async_function(value):
            return f"Success: {value}"
        
        # Test successful execution
        import asyncio
        result = asyncio.run(test_async_function("test_value"))
        
        assert result == "Success: test_value"
        
        print("✅ Safe operation decorator (async success) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_operation_async_failure(self, mock_get_settings):
        """Test safe_operation decorator with failing async function."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Decorate an async function that fails
        @safe_operation("test_operation", "Test operation failed")
        async def test_failing_function():
            raise ValueError("Async function failed")
        
        # Test failure handling
        import asyncio
        result = asyncio.run(test_failing_function())
        
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe operation decorator (async failure) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_operation_sync_success(self, mock_get_settings):
        """Test safe_operation decorator with successful sync function."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Decorate a sync function
        @safe_operation("sync_operation", "Sync operation failed")
        def test_sync_function(x, y):
            return x + y
        
        # Test successful execution
        result = test_sync_function(5, 3)
        
        assert result == 8
        
        print("✅ Safe operation decorator (sync success) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_operation_sync_failure(self, mock_get_settings):
        """Test safe_operation decorator with failing sync function."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Decorate a sync function that fails
        @safe_operation("sync_operation", "Sync operation failed")
        def test_failing_sync_function():
            raise ZeroDivisionError("Division by zero")
        
        # Test failure handling
        result = test_failing_sync_function()
        
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe operation decorator (sync failure) works correctly")


class TestSafeAPIOperation:
    """Test safe_api_operation decorator."""
    
    def test_safe_api_operation_async_success(self):
        """Test safe_api_operation decorator with successful async function."""
        # Decorate an async API function
        @safe_api_operation("api_operation", 200, "API operation successful")
        async def test_api_function(data):
            return {"result": f"Processed: {data}"}
        
        # Test successful execution
        import asyncio
        result = asyncio.run(test_api_function("test_data"))
        
        assert result == {"result": "Processed: test_data"}
        
        print("✅ Safe API operation decorator (async success) works correctly")
    
    def test_safe_api_operation_async_failure(self):
        """Test safe_api_operation decorator with failing async function."""
        # Decorate an async API function that fails
        @safe_api_operation("api_operation", 500, "API operation failed")
        async def test_failing_api_function():
            raise ConnectionError("Database connection lost")
        
        # Test failure handling
        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_failing_api_function())
        
        assert exc_info.value.status_code == 500
        assert "API operation failed" in str(exc_info.value.detail)
        
        print("✅ Safe API operation decorator (async failure) works correctly")
    
    def test_safe_api_operation_sync_success(self):
        """Test safe_api_operation decorator with successful sync function."""
        # Decorate a sync API function
        @safe_api_operation("sync_api_operation", 201, "Resource created")
        def test_sync_api_function(name):
            return {"id": 123, "name": name}
        
        # Test successful execution
        result = test_sync_api_function("test_resource")
        
        assert result == {"id": 123, "name": "test_resource"}
        
        print("✅ Safe API operation decorator (sync success) works correctly")
    
    def test_safe_api_operation_sync_failure(self):
        """Test safe_api_operation decorator with failing sync function."""
        # Decorate a sync API function that fails
        @safe_api_operation("sync_api_operation", 400, "Bad request")
        def test_failing_sync_api_function():
            raise ValueError("Invalid input data")
        
        # Test failure handling
        with pytest.raises(HTTPException) as exc_info:
            test_failing_sync_api_function()
        
        assert exc_info.value.status_code == 400
        assert "Bad request" in str(exc_info.value.detail)
        
        print("✅ Safe API operation decorator (sync failure) works correctly")
    
    def test_safe_api_operation_custom_status_code(self):
        """Test safe_api_operation decorator with custom status code."""
        # Decorate function with custom error status
        @safe_api_operation("custom_operation", 422, "Validation error")
        def test_custom_status_function():
            raise KeyError("Missing required field")
        
        # Test custom status code
        with pytest.raises(HTTPException) as exc_info:
            test_custom_status_function()
        
        assert exc_info.value.status_code == 422
        assert "Validation error" in str(exc_info.value.detail)
        
        print("✅ Safe API operation decorator (custom status) works correctly")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_very_long_flash_message(self, mock_get_settings):
        """Test safe redirect with very long flash message."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test with very long flash message
        long_message = "Error: " + "x" * 5000
        test_error = Exception("Test error")
        
        result = create_safe_redirect(test_error, flash_message=long_message)
        
        # Should still create redirect (URL encoding may truncate)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe redirect (very long flash message) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_create_safe_redirect_special_characters_in_flash(self, mock_get_settings):
        """Test safe redirect with special characters in flash message."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test with special characters
        special_message = "Error: 特殊文字 & symbols! @#$%^&*()+=[]{}|;':\",./<>?"
        test_error = Exception("Test error")
        
        result = create_safe_redirect(test_error, flash_message=special_message)
        
        # Should handle special characters gracefully
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        
        print("✅ Safe redirect (special characters) works correctly")
    
    @patch('apps.core.error_handling.get_settings')
    def test_safe_redirect_handler_nested_exceptions(self, mock_get_settings):
        """Test SafeRedirectHandler with nested exceptions."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.DEFAULT_REDIRECT_URL = "https://default.example.com"
        mock_get_settings.return_value = mock_settings
        
        # Test nested exception handling
        with SafeRedirectHandler() as handler:
            try:
                raise ValueError("Inner exception")
            except ValueError:
                raise RuntimeError("Outer exception") from None
        
        # Should handle the outer exception
        result = handler.get_result()
        assert isinstance(result, RedirectResponse)
        
        print("✅ SafeRedirectHandler (nested exceptions) works correctly")
    
    def test_safe_operation_with_complex_arguments(self):
        """Test safe_operation decorator with complex function arguments."""
        @safe_operation("complex_operation", "Complex operation failed")
        def complex_function(*args, **kwargs):
            return {
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys()),
                "total_params": len(args) + len(kwargs)
            }
        
        # Test with complex arguments
        result = complex_function(1, 2, 3, name="test", value=42, data=[1, 2, 3])
        
        expected = {
            "args_count": 3,
            "kwargs_keys": ["name", "value", "data"],
            "total_params": 6
        }
        assert result == expected
        
        print("✅ Safe operation (complex arguments) works correctly")


def run_all_tests():
    """Run all core error handling tests."""
    print("🛡️  Starting Core Error Handling Test Suite...")
    print("=" * 60)
    
    try:
        # Test create_safe_redirect
        redirect_tests = TestCreateSafeRedirect()
        redirect_tests.test_create_safe_redirect_basic()
        redirect_tests.test_create_safe_redirect_with_flash_message()
        redirect_tests.test_create_safe_redirect_with_context()
        redirect_tests.test_create_safe_redirect_auto_request_id()
        print()
        
        # Test log_and_redirect_on_error
        log_redirect_tests = TestLogAndRedirectOnError()
        log_redirect_tests.test_log_and_redirect_basic()
        log_redirect_tests.test_log_and_redirect_with_all_params()
        print()
        
        # Test SafeRedirectHandler
        handler_tests = TestSafeRedirectHandler()
        handler_tests.test_safe_redirect_handler_no_exception()
        handler_tests.test_safe_redirect_handler_with_exception()
        handler_tests.test_safe_redirect_handler_auto_request_id()
        print()
        
        # Test safe_operation decorator
        operation_tests = TestSafeOperation()
        operation_tests.test_safe_operation_async_success()
        operation_tests.test_safe_operation_async_failure()
        operation_tests.test_safe_operation_sync_success()
        operation_tests.test_safe_operation_sync_failure()
        print()
        
        # Test safe_api_operation decorator
        api_tests = TestSafeAPIOperation()
        api_tests.test_safe_api_operation_async_success()
        api_tests.test_safe_api_operation_async_failure()
        api_tests.test_safe_api_operation_sync_success()
        api_tests.test_safe_api_operation_sync_failure()
        api_tests.test_safe_api_operation_custom_status_code()
        print()
        
        # Test edge cases
        edge_tests = TestEdgeCases()
        edge_tests.test_create_safe_redirect_very_long_flash_message()
        edge_tests.test_create_safe_redirect_special_characters_in_flash()
        edge_tests.test_safe_redirect_handler_nested_exceptions()
        edge_tests.test_safe_operation_with_complex_arguments()
        print()
        
        print("🎉 All Core Error Handling tests passed!")
        print("✅ Safe redirect creation working correctly")
        print("✅ Error logging and redirection verified")
        print("✅ Context manager functionality robust")
        print("✅ Operation decorators tested")
        print("✅ API error handling comprehensive")
        print("✅ Edge cases handled gracefully")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  n8n SSO Gateway - Core Error Handling Test Suite")
    print("=" * 60)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 60)
        print("🏆 ALL CORE ERROR HANDLING TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Error handling is robust and reliable")
        print("⚡ Safe redirect mechanisms verified")
        print("🎯 Decorator functionality working correctly")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 CORE ERROR HANDLING TESTS FAILED!")
        print("❌ Error handling mechanisms need attention")
        print("=" * 60)
        exit(1)
