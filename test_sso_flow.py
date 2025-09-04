#!/usr/bin/env python3
"""
Test script to validate the n8n SSO flow end-to-end.
This script simulates a Casdoor authentication and tests the n8n cookie extraction.
"""

import asyncio
import httpx
from apps.integrations.n8n_client import N8NClient
from apps.auth.services import extract_n8n_auth_cookie
from conf.settings import get_settings

async def test_n8n_cookie_extraction():
    """Test n8n authentication and cookie extraction."""
    settings = get_settings()
    
    print(f"🔍 Testing n8n SSO flow with base URL: {settings.N8N_BASE_URL}")
    
    if not settings.N8N_OWNER_EMAIL or not settings.N8N_OWNER_PASSWORD:
        print("❌ N8N_OWNER_EMAIL and N8N_OWNER_PASSWORD must be set in .env for testing")
        return False
    
    # Test n8n login and cookie extraction
    n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
    
    try:
        print(f"🔐 Attempting login for: {settings.N8N_OWNER_EMAIL}")
        
        # Login to n8n
        response = n8n_client.login_user(
            email=settings.N8N_OWNER_EMAIL,
            password=settings.N8N_OWNER_PASSWORD
        )
        
        print(f"✅ Login response status: {response.status_code}")
        print(f"📄 Response headers: {dict(response.headers)}")
        
        # Extract auth cookie
        auth_cookie = extract_n8n_auth_cookie(response)
        
        if auth_cookie:
            print(f"🍪 Successfully extracted n8n-auth cookie: {auth_cookie[:20]}...")
            print(f"📏 Cookie length: {len(auth_cookie)}")
            
            # Verify cookie works by making an authenticated request
            print("🧪 Testing cookie validity...")
            
            authenticated_client = httpx.Client(
                base_url=str(settings.N8N_BASE_URL),
                cookies={"n8n-auth": auth_cookie},
                timeout=10.0
            )
            
            try:
                # Test accessing user info
                user_response = authenticated_client.get("/rest/login")
                print(f"👤 User info request status: {user_response.status_code}")
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    print(f"✅ Cookie is valid! User: {user_data.get('data', {}).get('email', 'unknown')}")
                    return True
                else:
                    print(f"❌ Cookie validation failed: {user_response.text}")
                    return False
                    
            except Exception as e:
                print(f"❌ Error testing cookie: {e}")
                return False
            finally:
                authenticated_client.close()
        else:
            print("❌ Failed to extract n8n-auth cookie")
            print("🔍 Available headers:")
            for header, value in response.headers.items():
                if 'cookie' in header.lower():
                    print(f"   {header}: {value}")
            return False
            
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False
    finally:
        n8n_client.close()

async def main():
    """Main test function."""
    print("🚀 Starting n8n SSO flow test")
    print("=" * 50)
    
    success = await test_n8n_cookie_extraction()
    
    print("=" * 50)
    if success:
        print("✅ All tests passed! n8n SSO flow should work properly.")
    else:
        print("❌ Tests failed. Check the configuration and n8n setup.")
    
    return success

if __name__ == "__main__":
    import sys
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
