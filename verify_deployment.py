#!/usr/bin/env python3
"""
Pre-deployment verification script.
Checks if all dependencies are correct and the application can start.
"""

def check_imports():
    """Test critical imports."""
    try:
        from apps.main import app
        from apps.auth.services import handle_casdoor_callback, extract_n8n_auth_cookie  
        from apps.integrations.n8n_client import N8NClient
        from conf.settings import get_settings
        print("✅ All critical imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def check_settings():
    """Test settings loading."""
    try:
        from conf.settings import get_settings
        settings = get_settings()
        
        required_settings = [
            'N8N_BASE_URL', 'N8N_DB_DSN', 
            'CASDOOR_ENDPOINT', 'CASDOOR_CLIENT_ID', 'CASDOOR_CLIENT_SECRET'
        ]
        
        missing = []
        for setting in required_settings:
            if not getattr(settings, setting, None):
                missing.append(setting)
        
        if missing:
            print(f"❌ Missing required settings: {', '.join(missing)}")
            return False
            
        print("✅ All required settings present")
        return True
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False

def main():
    print("🚀 Pre-deployment verification")
    print("=" * 40)
    
    checks = [
        ("Import checks", check_imports),
        ("Settings checks", check_settings),
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\n📋 Running {name}...")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Ready for deployment!")
        print("\n🚀 Deploy with:")
        print("   pip install -r requirements.txt")
        print("   uvicorn apps.main:app --host 0.0.0.0 --port 8000")
    else:
        print("❌ CHECKS FAILED - Fix issues before deployment")
    
    return all_passed

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
