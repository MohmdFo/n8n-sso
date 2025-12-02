#!/usr/bin/env python3
"""
Test script for template workflow creation functionality.
"""

import sys
import asyncio
import tempfile
import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch

# Add the project root to the Python path
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.integrations.template_manager import WorkflowTemplate, TemplateManager, get_template_manager
from apps.integrations.n8n_db import CasdoorProfile, create_template_workflow_for_user


def test_workflow_template():
    """Test WorkflowTemplate class."""
    print("Testing WorkflowTemplate...")
    
    # Create a temporary template file
    sample_template = {
        "name": "Test Workflow",
        "nodes": [
            {
                "id": "test-node",
                "type": "n8n-nodes-base.start",
                "credentials": {
                    "testApi": {"id": "user123", "name": "User Creds"}
                },
                "webhookId": "webhook123"
            }
        ],
        "connections": {},
        "settings": {"timezone": "UTC"},
        "active": True,
        "meta": {"templateCredsSetupCompleted": True}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_template, f)
        temp_path = f.name
    
    try:
        # Test template loading
        template = WorkflowTemplate("test-template", temp_path, "Test Description")
        
        # Test data loading
        data = template.data
        assert data["name"] == "Test Workflow"
        assert len(data["nodes"]) == 1
        print("✅ Template data loading works")
        
        # Test user preparation
        user_data = template.prepare_for_user("user@example.com")
        
        # Check that credentials were removed
        assert "credentials" not in user_data["nodes"][0]
        print("✅ Credentials removed from template")
        
        # Check that webhook ID was removed
        assert "webhookId" not in user_data["nodes"][0]
        print("✅ Webhook ID removed from template")
        
        # Check that workflow is inactive
        assert user_data["active"] is False
        print("✅ Template set to inactive for user")
        
        # Check that name was updated
        assert "(Template)" in user_data["name"]
        print("✅ Template name updated")
        
        # Check that meta was reset
        assert user_data["meta"]["templateCredsSetupCompleted"] is False
        print("✅ Meta data reset")
        
        print("✅ WorkflowTemplate test passed!")
        
    finally:
        # Cleanup
        Path(temp_path).unlink()


def test_template_manager():
    """Test TemplateManager class."""
    print("\nTesting TemplateManager...")
    
    # Create a temporary templates directory
    with tempfile.TemporaryDirectory() as temp_dir:
        templates_dir = Path(temp_dir)
        
        # Create a sample template
        template1_data = {
            "name": "Sample Template 1",
            "nodes": [],
            "connections": {}
        }
        
        template1_path = templates_dir / "sample-template-1.json"
        with open(template1_path, 'w') as f:
            json.dump(template1_data, f)
        
        # Create another template
        template2_data = {
            "name": "02 - Google Calendar & Telegram",
            "nodes": [],
            "connections": {}
        }
        
        template2_path = templates_dir / "02-Google-Calendar&Telegram.json"
        with open(template2_path, 'w') as f:
            json.dump(template2_data, f)
        
        # Mock the TEMPLATES_DIR
        with patch('apps.integrations.template_manager.TEMPLATES_DIR', templates_dir):
            manager = TemplateManager()
            
            # Test template discovery
            templates = manager.list_templates()
            assert len(templates) == 2
            print("✅ Template discovery works")
            
            # Test getting specific template
            template = manager.get_template("sample-template-1")
            assert template is not None
            assert template.name == "sample-template-1"
            print("✅ Template retrieval works")
            
            # Test default template
            default_template = manager.get_default_template()
            assert default_template is not None
            assert default_template.name == "02-Google-Calendar&Telegram"
            print("✅ Default template selection works")
            
            print("✅ TemplateManager test passed!")


async def test_create_template_workflow():
    """Test creating template workflow for user."""
    print("\nTesting create_template_workflow_for_user...")
    
    # Create a mock template
    sample_template = {
        "name": "Test Workflow for User",
        "nodes": [
            {
                "id": "test-node",
                "type": "n8n-nodes-base.start",
                "parameters": {}
            }
        ],
        "connections": {},
        "settings": {"timezone": "UTC"},
        "pinData": {}
    }
    
    # Mock the template manager
    mock_template = WorkflowTemplate("test", "", "Test")
    mock_template._data = sample_template
    
    mock_template_manager = TemplateManager()
    mock_template_manager.templates = {"test": mock_template}
    
    # Mock the database connection
    mock_conn = AsyncMock()
    mock_execute = AsyncMock()
    mock_conn.execute = mock_execute
    
    with patch('apps.integrations.n8n_db.get_connection') as mock_get_conn, \
         patch('apps.integrations.n8n_db.get_template_manager', return_value=mock_template_manager):
        
        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        
        # Test the function
        user_id = uuid4()
        project_id = "test_project_123"
        user_email = "test@example.com"
        
        result = await create_template_workflow_for_user(
            user_id=user_id,
            project_id=project_id,
            user_email=user_email
        )
        
        # Check that the function succeeded
        assert result is True
        print("✅ Template workflow creation succeeded")
        
        # Check that database operations were called
        assert mock_execute.call_count >= 3  # workflow insert + 2 relation inserts
        print("✅ Database operations called correctly")
        
        # Check that the workflow was prepared properly
        workflow_calls = [call for call in mock_execute.call_args_list 
                         if 'INSERT INTO workflow' in str(call)]
        assert len(workflow_calls) == 1
        print("✅ Workflow inserted into database")
        
        print("✅ create_template_workflow_for_user test passed!")


async def main():
    """Run all tests."""
    print("🧪 Testing Template Workflow Functionality")
    print("=" * 60)
    
    try:
        # Test components
        test_workflow_template()
        test_template_manager()
        await test_create_template_workflow()
        
        print("\n" + "=" * 60)
        print("🎉 All template workflow tests passed!")
        print("✅ Template loading and preparation works")
        print("✅ Template manager discovery works")
        print("✅ Database workflow creation works")
        print("✅ Ready to create workflows for new users!")
        print("=" * 60)
        
        return True
        
    except Exception as exc:
        print(f"\n❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)