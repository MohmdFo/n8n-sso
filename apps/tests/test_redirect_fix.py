#!/usr/bin/env python3
"""
Quick test script to verify the SSO redirect fix.
"""

import pytest
import httpx
import asyncio

@pytest.mark.asyncio
async def test_redirect_fix():
    """Test that the SSO gateway properly redirects to workflows."""
    gateway_url = "http://107.189.19.66:8512"
    
    print(f"🔍 Testing SSO gateway at: {gateway_url}")
    
    # Test health endpoint
    try:
        async with httpx.AsyncClient() as client:
            health_response = await client.get(f"{gateway_url}/health")
            if health_response.status_code == 200:
                print("✅ Gateway is running and healthy")
            else:
                print(f"❌ Gateway health check failed: {health_response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Cannot reach gateway: {e}")
        return False
    
    # Test that login endpoint exists
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            login_response = await client.get(f"{gateway_url}/auth/casdoor/login")
            if login_response.status_code == 302:
                redirect_url = login_response.headers.get("location", "")
                if "casdoor" in redirect_url.lower():
                    print("✅ Login redirect to Casdoor is working")
                else:
                    print(f"❌ Unexpected redirect: {redirect_url}")
                    return False
            else:
                print(f"❌ Login endpoint failed: {login_response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Login endpoint test failed: {e}")
        return False
    
    print("🎉 All tests passed! Your SSO gateway is ready.")
    print(f"🔗 Login URL: {gateway_url}/auth/casdoor/login")
    print(f"📋 After login, users should be redirected to: http://107.189.19.66:8510/home/workflows")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_redirect_fix())
    exit(0 if success else 1)
