#!/usr/bin/env python3
"""
Test script to verify the Casdoor logout webhook functionality.
"""

import pytest
import asyncio
import httpx
import json

# Sample webhook payload (based on your Casdoor example)
SAMPLE_LOGOUT_WEBHOOK = {
    "id": 9078,
    "owner": "built-in",
    "name": "68f55b28-7380-46b1-9bde-64fe1576e3b3",
    "createdTime": "2022-01-01T01:03:42+08:00",
    "organization": "organization_sharif",
    "clientIp": "159.89.126.192",
    "user": "admin",
    "method": "POST",
    "requestUri": "/api/logout",
    "action": "logout",  # This is the key field
    "isTriggered": False,
    "object": '{"owner":"admin","name":"test_logout","organization":"organization_sharif"}',
    "extendedUser": {
        "name": "admin",
        "email": "admin@ai-lab.ir",
        "displayName": "Admin User",
        "firstName": "Admin",
        "lastName": "User"
    }
}

@pytest.mark.asyncio
async def test_webhook_endpoint():
    """Test the webhook endpoint with a sample logout event."""
    gateway_url = "http://107.189.19.66:8512"
    webhook_url = f"{gateway_url}/auth/casdoor/webhook"
    
    print(f"🧪 Testing webhook endpoint: {webhook_url}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send the webhook payload
            response = await client.post(
                webhook_url,
                json=SAMPLE_LOGOUT_WEBHOOK,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Webhook processed successfully!")
                print(f"📄 Response: {json.dumps(result, indent=2)}")
                return True
            else:
                print(f"❌ Webhook failed with status: {response.status_code}")
                print(f"📄 Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Webhook test failed: {e}")
        return False

@pytest.mark.asyncio
async def test_manual_logout():
    """Test the manual logout endpoint."""
    gateway_url = "http://107.189.19.66:8512"
    logout_url = f"{gateway_url}/auth/casdoor/logout"
    
    print(f"🔓 Testing manual logout endpoint: {logout_url}")
    
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            response = await client.get(logout_url)
            
            if response.status_code == 302:
                redirect_url = response.headers.get("location", "")
                print("✅ Manual logout redirect working!")
                print(f"🔗 Redirects to: {redirect_url}")
                
                # Check if cookies are being cleared
                set_cookies = response.headers.get_list("set-cookie") or []
                cookie_cleared = any("n8n-auth" in cookie and "Max-Age=0" in cookie for cookie in set_cookies)
                if cookie_cleared:
                    print("🍪 Cookie clearing detected!")
                else:
                    print("⚠️  No cookie clearing detected in response")
                
                return True
            else:
                print(f"❌ Manual logout failed with status: {response.status_code}")
                print(f"📄 Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Manual logout test failed: {e}")
        return False

@pytest.mark.asyncio
async def test_health_check():
    """Test that the gateway is running."""
    gateway_url = "http://107.189.19.66:8512"
    health_url = f"{gateway_url}/health"
    
    print(f"💚 Testing health endpoint: {health_url}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)
            
            if response.status_code == 200:
                print("✅ Gateway is healthy and running!")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Cannot reach gateway: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing Casdoor Logout Webhook Integration")
    print("=" * 50)
    
    # Test 1: Health check
    health_ok = await test_health_check()
    if not health_ok:
        print("❌ Cannot proceed - gateway is not running")
        return False
    
    print()
    
    # Test 2: Webhook endpoint
    webhook_ok = await test_webhook_endpoint()
    
    print()
    
    # Test 3: Manual logout
    logout_ok = await test_manual_logout()
    
    print()
    print("=" * 50)
    
    if webhook_ok and logout_ok:
        print("🎉 All tests passed! Logout webhook integration is working!")
        print()
        print("📋 Setup Instructions:")
        print(f"1. In Casdoor, create a webhook pointing to:")
        print(f"   http://107.189.19.66:8512/auth/casdoor/webhook")
        print("2. Set the webhook to trigger on 'logout' events")
        print("3. Set content type to 'application/json'")
        print("4. Enable the webhook for your organization")
        return True
    else:
        print("❌ Some tests failed. Check the logs and fix issues.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
