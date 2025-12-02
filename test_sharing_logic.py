#!/usr/bin/env python3
"""Test the exact sharing logic that's failing."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from apps.integrations.n8n_db import get_connection
from sqlalchemy import text
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

async def test_sharing_logic():
    """Test the exact sharing logic that's failing in production."""
    async with get_connection() as conn:
        try:
            # Get the latest workflow and user
            latest_workflow = await conn.execute(text('''
                SELECT id, name, "createdAt" 
                FROM workflow_entity 
                ORDER BY "createdAt" DESC 
                LIMIT 1
            '''))
            workflow_row = latest_workflow.fetchone()
            workflow_id = workflow_row.id
            
            latest_user = await conn.execute(text('''
                SELECT id, email, "createdAt"
                FROM "user"
                ORDER BY "createdAt" DESC
                LIMIT 1
            '''))
            user_row = latest_user.fetchone()
            user_id = user_row.id
            
            # Get user's project
            user_project = await conn.execute(text('''
                SELECT p.id, p.name, p."createdAt"
                FROM project p
                JOIN project_relation pr ON p.id = pr."projectId"
                WHERE pr."userId" = :userId
                ORDER BY p."createdAt" DESC
                LIMIT 1
            '''), {"userId": user_id})
            project_row = user_project.fetchone()
            project_id = project_row.id
            
            print(f"Testing sharing for:")
            print(f"  Workflow: {workflow_id} ({workflow_row.name})")
            print(f"  User: {user_row.email}")
            print(f"  Project: {project_id} ({project_row.name})")
            
            # Test 1: Check if shared_workflow table exists in relation_tables query
            print(f"\n1. Testing relation_tables query...")
            relation_tables_result = await conn.execute(text('''
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('shared_workflow', 'workflow_entity_relation')
            '''))
            relation_tables = [row.table_name for row in relation_tables_result.fetchall()]
            print(f"   Found tables: {relation_tables}")
            
            if "shared_workflow" not in relation_tables:
                print(f"   ❌ shared_workflow table not found!")
                return
            
            # Test 2: Check if workflow already exists
            print(f"\n2. Testing existing share check...")
            try:
                existing_result = await conn.execute(
                    text('SELECT * FROM shared_workflow WHERE "workflowId" = :workflowId'),
                    {"workflowId": workflow_id}
                )
                existing = existing_result.fetchall()
                print(f"   Existing shares: {len(existing)}")
                for i, row in enumerate(existing):
                    print(f"     Row {i}: workflowId={row.workflowId}, projectId={row.projectId}, role={row.role}")
            except Exception as e:
                print(f"   ❌ Existing check failed: {e}")
                return
            
            # Test 3: Try the actual insert (if not already shared)
            if not existing:
                print(f"\n3. Testing insert...")
                try:
                    await conn.execute(
                        text('''
                            INSERT INTO shared_workflow ("workflowId", "projectId", "role") 
                            VALUES (:workflowId, :projectId, :role)
                        '''),
                        {
                            "workflowId": workflow_id,
                            "projectId": project_id,
                            "role": "workflow:owner"
                        }
                    )
                    print(f"   ✅ Insert successful!")
                    
                    # Verify
                    verify_result = await conn.execute(
                        text('SELECT * FROM shared_workflow WHERE "workflowId" = :workflowId'),
                        {"workflowId": workflow_id}
                    )
                    verify = verify_result.fetchone()
                    print(f"   Verified: workflowId={verify.workflowId}, projectId={verify.projectId}, role={verify.role}")
                    
                except Exception as e:
                    print(f"   ❌ Insert failed: {e}")
                    print(f"   Error type: {type(e).__name__}")
                    print(f"   Error details: {repr(e)}")
            else:
                print(f"\n3. Workflow already shared, skipping insert test")
                
        except Exception as e:
            print(f"Test failed: {e}")
            print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_sharing_logic())