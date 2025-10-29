#!/usr/bin/env python3
"""
Test script to send a webhook payload similar to what Casdoor would send
to debug the user email extraction issue.
"""

import pytest
import httpx
import json

# Test webhook payload (based on what Casdoor typically sends)
test_payload = {
    "id": 12345,
    "action": "logout",
    "user": "admin",
    "organization": "organization_sharif",
    "clientIp": "192.168.1.1",
    "method": "GET",
    "requestUri": "/logout",
    "isTriggered": True,
    "object": {
        "name": "admin",
        "email": "admin@ai-lab.ir",
        "displayName": "Admin User",
        "firstName": "Admin",
        "lastName": "User"
    },
    "extendedUser": {
        "name": "admin", 
        "email": "admin@ai-lab.ir",
        "displayName": "Admin User",
        "firstName": "Admin",
        "lastName": "User"
    }
}

# Also test a minimal payload to see what Casdoor actually sends
minimal_payload = {
    "id": 12346,
    "action": "logout",
    "user": "admin",
    "organization": "organization_sharif"
}

@pytest.mark.parametrize("payload,description", [
    (test_payload, "Complete payload with object and extendedUser"),
    (minimal_payload, "Minimal payload without email fields")
])
def test_webhook(payload, description):
    """Send test webhook payload."""
    print(f"\n{'='*50}")
    print(f"Testing: {description}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*50}")
    
    try:
        response = httpx.post(
            "http://107.189.19.66:8512/v1/auth/casdoor/webhook",
            json=payload,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            try:
                json_response = response.json()
                print(f"JSON Response: {json.dumps(json_response, indent=2)}")
            except:
                pass
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing Casdoor Logout Webhook Payload Handling")
    
    # Test 1: Full payload with extended user
    success1 = test_webhook(test_payload, "Full payload with extendedUser")
    
    # Test 2: Minimal payload (like what might actually be sent)
    success2 = test_webhook(minimal_payload, "Minimal payload (no extendedUser)")
    
    print(f"\n{'='*50}")
    print("TEST SUMMARY:")
    print(f"Full payload test: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Minimal payload test: {'✅ PASS' if success2 else '❌ FAIL'}")
    
    if not success1 and not success2:
        print("\n🔍 DEBUGGING TIPS:")
        print("1. Check if the SSO gateway is running: docker logs n8n-sso-gateway")
        print("2. Check if the webhook endpoint is accessible")
        print("3. Look at the gateway logs for detailed error messages")
    elif success1 and not success2:
        print("\n✅ The webhook works with full payload but not minimal payload")
        print("This suggests Casdoor is not sending the extendedUser field properly")
        print("Check your Casdoor webhook configuration!")
