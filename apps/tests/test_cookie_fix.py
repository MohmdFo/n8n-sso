#!/usr/bin/env python3
"""
Test script to verify cookie extraction and domain parsing improvements.
"""
import pytest
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apps.auth.services import extract_n8n_auth_cookie
from apps.integrations.n8n_client import N8NClient
from conf.settings import get_settings
from urllib.parse import urlparse


def test_domain_parsing():
    """Test domain parsing logic."""
    print("🔍 Testing domain parsing logic...")
    
    test_urls = [
        "https://n8n.ai-lab.ir",
        "http://n8n.ai-lab.ir",
        "https://localhost:8510",
        "http://107.189.19.66:8510",
        "https://n8n.example.com:443",
    ]
    
    for url in test_urls:
        parsed_url = urlparse(url)
        cookie_domain = parsed_url.hostname
        is_secure = parsed_url.scheme == "https"
        
        # Apply the same logic as in the fixed code
        if not cookie_domain or cookie_domain == "localhost":
            cookie_domain = None
            
        print(f"  URL: {url}")
        print(f"    Parsed hostname: {parsed_url.hostname}")
        print(f"    Cookie domain: {cookie_domain}")
        print(f"    Is secure: {is_secure}")
        print(f"    Scheme: {parsed_url.scheme}")
        print()


@pytest.mark.asyncio
async def test_n8n_login_with_cookie_extraction():
    """Test the full n8n login and cookie extraction process."""
    print("🧪 Testing n8n login and cookie extraction...")
    
    settings = get_settings()
    
    if not settings.N8N_OWNER_EMAIL or not settings.N8N_OWNER_PASSWORD:
        print("❌ N8N_OWNER_EMAIL and N8N_OWNER_PASSWORD must be set for testing")
        return False
    
    n8n_client = N8NClient(base_url=str(settings.N8N_BASE_URL))
    
    try:
        print(f"🔐 Testing login for: {settings.N8N_OWNER_EMAIL}")
        print(f"🌐 n8n Base URL: {settings.N8N_BASE_URL}")
        
        # Test login and cookie extraction
        response = n8n_client.login_user(
            email=settings.N8N_OWNER_EMAIL,
            password=settings.N8N_OWNER_PASSWORD
        )
        
        print(f"✅ Login response status: {response.status_code}")
        print(f"📄 Response headers: {dict(response.headers)}")
        
        # Test our enhanced cookie extraction
        auth_cookie = extract_n8n_auth_cookie(response)
        
        if auth_cookie:
            print(f"🍪 Cookie extracted successfully: {auth_cookie[:20]}...{auth_cookie[-10:]}")
            print(f"📏 Cookie length: {len(auth_cookie)}")
            
            # Test domain parsing with the actual URL
            from urllib.parse import urlparse
            parsed_url = urlparse(str(settings.N8N_BASE_URL))
            cookie_domain = parsed_url.hostname
            
            if not cookie_domain or cookie_domain == "localhost":
                cookie_domain = None
                
            print(f"🏷️  Calculated cookie domain: {cookie_domain}")
            print(f"🔒 Would use secure: {parsed_url.scheme == 'https'}")
            
            return True
        else:
            print("❌ Failed to extract cookie")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        n8n_client.close()


async def main():
    """Run all tests."""
    print("🚀 Running cookie fix verification tests...\n")
    
    # Test 1: Domain parsing
    test_domain_parsing()
    
    # Test 2: Cookie extraction
    success = await test_n8n_login_with_cookie_extraction()
    
    print("\n" + "="*50)
    if success:
        print("✅ All tests passed! Cookie extraction improvements are working.")
    else:
        print("❌ Some tests failed. Check the configuration and n8n connectivity.")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
