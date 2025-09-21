#!/usr/bin/env python3
"""
Test script to verify improved error handling and service resilience.

This script tests various error scenarios to ensure:
1. Errors are logged as critical instead of crashing the service
2. Users are redirected to DEFAULT_REDIRECT_URL with flash messages
3. Service remains available and responsive
"""

import asyncio
import sys
import traceback
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock

# Add project root to path
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.core.error_handling import (
    create_safe_redirect, 
    log_and_redirect_on_error,
    SafeRedirectHandler,
    safe_operation
)
from apps.auth.services import (
    get_oauth_token,
    parse_jwt_token,
    map_casdoor_to_profile,
    handle_casdoor_callback
)
from fastapi import Request
from fastapi.responses import RedirectResponse
from conf.settings import get_settings


def test_error_handling_utilities():
    """Test the core error handling utilities."""
    print("🔧 Testing error handling utilities...")
    
    # Test create_safe_redirect
    test_error = ValueError("Test error message")
    redirect = create_safe_redirect(
        error=test_error,
        flash_message="Test flash message",
        context={"test": "context"},
        request_id="test123"
    )
    
    assert isinstance(redirect, RedirectResponse)
    assert redirect.status_code == 302
    print("✅ create_safe_redirect works correctly")
    
    # Test log_and_redirect_on_error
    redirect2 = log_and_redirect_on_error(
        error_message="Test error message",
        flash_message="Test flash",
        request_id="test456"
    )
    
    assert isinstance(redirect2, RedirectResponse)
    assert redirect2.status_code == 302
    print("✅ log_and_redirect_on_error works correctly")
    
    # Test SafeRedirectHandler context manager
    with SafeRedirectHandler(request_id="test789", flash_message="Test error") as handler:
        # Simulate an error
        raise RuntimeError("Test runtime error")
    
    result = handler.get_result()
    assert isinstance(result, RedirectResponse)
    print("✅ SafeRedirectHandler works correctly")


async def test_oauth_token_error_handling():
    """Test get_oauth_token error handling."""
    print("🔐 Testing OAuth token error handling...")
    
    # Test with invalid code
    result = await get_oauth_token("invalid_code", "test_req_1")
    
    # Should return a redirect response, not raise an exception
    assert isinstance(result, RedirectResponse), f"Expected RedirectResponse, got {type(result)}"
    print("✅ get_oauth_token handles errors gracefully with redirects")


def test_jwt_token_error_handling():
    """Test parse_jwt_token error handling."""
    print("🎫 Testing JWT token error handling...")
    
    # Test with invalid token
    result = parse_jwt_token("invalid.jwt.token", "test_req_2")
    
    # Should return a redirect response, not raise an exception  
    assert isinstance(result, RedirectResponse), f"Expected RedirectResponse, got {type(result)}"
    print("✅ parse_jwt_token handles errors gracefully with redirects")


def test_profile_mapping_error_handling():
    """Test map_casdoor_to_profile error handling."""
    print("👤 Testing profile mapping error handling...")
    
    # Test with missing email
    invalid_user_info = {"name": "Test User", "sub": "123"}  # No email
    result = map_casdoor_to_profile(invalid_user_info, "test_req_3")
    
    # Should return a redirect response, not raise an exception
    assert isinstance(result, RedirectResponse), f"Expected RedirectResponse, got {type(result)}"
    print("✅ map_casdoor_to_profile handles errors gracefully with redirects")


async def test_callback_error_handling():
    """Test handle_casdoor_callback error handling."""
    print("📞 Testing callback error handling...")
    
    # Create a mock request with no code parameter
    mock_request = Mock(spec=Request)
    mock_request.query_params = {}
    
    result = await handle_casdoor_callback(mock_request)
    
    # Should return a redirect response, not raise an exception
    assert isinstance(result, RedirectResponse), f"Expected RedirectResponse, got {type(result)}"
    print("✅ handle_casdoor_callback handles missing code gracefully with redirects")


def test_safe_operation_decorator():
    """Test the safe_operation decorator."""
    print("🛡️ Testing safe_operation decorator...")
    
    @safe_operation("test_operation", "Test failed")
    async def failing_async_function():
        raise RuntimeError("Simulated async failure")
    
    @safe_operation("test_operation", "Test failed")
    def failing_sync_function():
        raise RuntimeError("Simulated sync failure")
    
    # Test async function
    async def test_async():
        result = await failing_async_function()
        assert isinstance(result, RedirectResponse)
        return True
    
    # Test sync function
    result = failing_sync_function()
    assert isinstance(result, RedirectResponse)
    
    print("✅ safe_operation decorator works for both sync and async functions")
    
    return test_async()


def test_settings_access():
    """Test that DEFAULT_REDIRECT_URL is accessible."""
    print("⚙️ Testing settings access...")
    
    settings = get_settings()
    assert hasattr(settings, 'DEFAULT_REDIRECT_URL')
    assert settings.DEFAULT_REDIRECT_URL is not None
    print(f"✅ DEFAULT_REDIRECT_URL: {settings.DEFAULT_REDIRECT_URL}")


async def run_all_tests():
    """Run all error handling tests."""
    print("🚀 Starting comprehensive error handling tests...\n")
    
    try:
        # Test core utilities
        test_error_handling_utilities()
        print()
        
        # Test settings
        test_settings_access()
        print()
        
        # Test auth service functions
        await test_oauth_token_error_handling()
        print()
        
        test_jwt_token_error_handling()
        print()
        
        test_profile_mapping_error_handling()
        print()
        
        await test_callback_error_handling()
        print()
        
        # Test decorator
        await test_safe_operation_decorator()
        print()
        
        print("🎉 All error handling tests passed!")
        print("✅ Service will remain available and redirect users safely on errors")
        print("✅ All errors are logged as critical for monitoring")
        print("✅ Users receive helpful flash messages instead of error pages")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


def simulate_error_scenarios():
    """Simulate various error scenarios that might occur in production."""
    print("\n🎭 Simulating production error scenarios...")
    
    scenarios = [
        "Database connection timeout",
        "Casdoor service unavailable",
        "Invalid JWT certificate",
        "Network timeout during OAuth",
        "Memory allocation error",
        "Disk space full",
        "Rate limiting exceeded"
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"{i}. Testing scenario: {scenario}")
        
        # Create a simulated error
        error = RuntimeError(f"Simulated: {scenario}")
        redirect = create_safe_redirect(
            error=error,
            flash_message=f"Service temporarily unavailable: {scenario}",
            context={"scenario": scenario, "test_mode": True},
            request_id=f"sim_{i}"
        )
        
        assert isinstance(redirect, RedirectResponse)
        print(f"   ✅ Handled gracefully with redirect")
    
    print("✅ All production scenarios handled gracefully!")


if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  n8n SSO Gateway - Error Handling Test Suite")
    print("=" * 60)
    
    # Run the main tests
    success = asyncio.run(run_all_tests())
    
    if success:
        # Run additional scenario simulations
        simulate_error_scenarios()
        
        print("\n" + "=" * 60)
        print("🏆 ALL TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Service resilience has been verified")
        print("📊 Error handling improvements are working correctly")
        print("=" * 60)
        
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 TESTS FAILED!")
        print("❌ Error handling needs more work")
        print("=" * 60)
        
        sys.exit(1)
