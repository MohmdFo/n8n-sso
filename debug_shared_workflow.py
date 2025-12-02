#!/usr/bin/env python3
"""Debug script to check shared_workflow table schema and fix sharing issue."""

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

async def debug_shared_workflow():
    """Debug shared_workflow table and check what's wrong."""
    async with get_connection() as conn:
        try:
            # Check schema
            schema_result = await conn.execute(text('''
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'shared_workflow'
                ORDER BY ordinal_position;
            '''))
            
            print("shared_workflow table schema:")
            for row in schema_result:
                print(f"  {row.column_name}: {row.data_type} (nullable: {row.is_nullable}, default: {row.column_default})")
            
            # Check existing entries
            existing_result = await conn.execute(text('SELECT * FROM shared_workflow LIMIT 5'))
            existing = existing_result.fetchall()
            print(f"\nExisting entries in shared_workflow ({len(existing)} shown):")
            for row in existing:
                print(f"  {dict(row)}")
            
            # Check if there's any constraint issues
            constraints_result = await conn.execute(text('''
                SELECT conname, contype, pg_get_constraintdef(oid)
                FROM pg_constraint 
                WHERE conrelid = 'shared_workflow'::regclass;
            '''))
            
            print(f"\nConstraints on shared_workflow:")
            for row in constraints_result:
                print(f"  {row.conname} ({row.contype}): {row.pg_get_constraintdef}")
                
            # Test a manual insert to see what happens
            test_workflow_id = "test_workflow_123"
            test_project_id = "test_project_123"
            
            # Clean up any existing test data first
            await conn.execute(text('''
                DELETE FROM shared_workflow 
                WHERE "workflowId" = :workflowId OR "projectId" = :projectId
            '''), {"workflowId": test_workflow_id, "projectId": test_project_id})
            
            print(f"\nTesting manual insert...")
            try:
                await conn.execute(text('''
                    INSERT INTO shared_workflow ("workflowId", "projectId", "role") 
                    VALUES (:workflowId, :projectId, :role)
                '''), {
                    "workflowId": test_workflow_id,
                    "projectId": test_project_id, 
                    "role": "workflow:owner"
                })
                print("  Manual insert SUCCESS!")
                
                # Clean up test data
                await conn.execute(text('''
                    DELETE FROM shared_workflow 
                    WHERE "workflowId" = :workflowId
                '''), {"workflowId": test_workflow_id})
                
            except Exception as e:
                print(f"  Manual insert FAILED: {e}")
                print(f"  Error type: {type(e).__name__}")
                
        except Exception as e:
            logger.error(f"Debug failed: {e}")
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_shared_workflow())