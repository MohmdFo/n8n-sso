#!/usr/bin/env python3
"""
Manually create a template workflow for an existing user to test the creation logic.
"""

import asyncio
import sys
import os
sys.path.insert(0, '.')

from apps.integrations.n8n_db import create_template_workflow_for_user, now_utc
from uuid import UUID

async def test_workflow_creation():
    """Test creating template workflow for the recent user."""
    
    # Recent user details from our investigation
    user_id = "7aeb86a3-9238-47a3-b1c2-638c21c28f65"  # This was in the error logs
    project_id = "z60onWyI451SUq5Z"  # Recent project for safa@gmail.com
    user_email = "safa@gmail.com"
    
    print(f"🧪 Testing template workflow creation for:")
    print(f"   User ID: {user_id}")
    print(f"   Project ID: {project_id}")  
    print(f"   Email: {user_email}")
    print("=" * 60)
    
    try:
        result = await create_template_workflow_for_user(
            user_id=UUID(user_id),
            project_id=project_id,
            user_email=user_email,
            now=now_utc()
        )
        
        if result:
            print("✅ Template workflow creation succeeded!")
        else:
            print("❌ Template workflow creation failed!")
            
        return result
        
    except Exception as exc:
        print(f"❌ Exception during template workflow creation: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("🔧 Manual Template Workflow Creation Test")
    print("=" * 60)
    
    success = asyncio.run(test_workflow_creation())
    
    if success:
        print("\n🎉 SUCCESS: Template workflow should now be visible in n8n!")
    else:
        print("\n💥 FAILED: Check the logs above for details")
        
    sys.exit(0 if success else 1)