#!/usr/bin/env python3
"""
Fix orphaned template workflows by associating them with their correct projects.
Run this script to fix any workflows that were created but not properly shared.
"""

import asyncio
import asyncpg
import sys
from datetime import datetime, timezone

async def fix_orphaned_workflows():
    dsn = 'postgresql://n8n:n8npass@144.172.110.149:5456/n8n'
    
    try:
        conn = await asyncpg.connect(dsn)
        
        print("🔍 Finding orphaned template workflows...")
        
        # Find workflows that exist but are not in shared_workflow
        orphaned_workflows = await conn.fetch('''
            SELECT w.id, w.name, w."createdAt"
            FROM workflow_entity w
            LEFT JOIN shared_workflow sw ON w.id = sw."workflowId"
            WHERE sw."workflowId" IS NULL
            AND w.name LIKE '%Template%'
            ORDER BY w."createdAt" DESC
        ''')
        
        if not orphaned_workflows:
            print("✅ No orphaned template workflows found!")
            await conn.close()
            return
        
        print(f"🔧 Found {len(orphaned_workflows)} orphaned template workflows:")
        for workflow in orphaned_workflows:
            print(f"  - {workflow['id']}: {workflow['name']} (created: {workflow['createdAt']})")
        
        # Find recent projects (likely owners of orphaned workflows)
        recent_projects = await conn.fetch('''
            SELECT id, name, "createdAt"
            FROM project
            WHERE type = 'personal'
            ORDER BY "createdAt" DESC
            LIMIT 10
        ''')
        
        print(f"\n📁 Recent projects:")
        for project in recent_projects:
            print(f"  - {project['id']}: {project['name']} (created: {project['createdAt']})")
        
        # Try to match workflows with projects based on creation time
        fixed_count = 0
        for workflow in orphaned_workflows:
            workflow_time = workflow['createdAt']
            
            # Find the project created closest in time (within 1 minute)
            closest_project = None
            min_time_diff = float('inf')
            
            for project in recent_projects:
                project_time = project['createdAt']
                time_diff = abs((workflow_time - project_time).total_seconds())
                
                if time_diff < min_time_diff and time_diff < 60:  # Within 1 minute
                    min_time_diff = time_diff
                    closest_project = project
            
            if closest_project:
                try:
                    # Insert the missing shared_workflow entry
                    await conn.execute('''
                        INSERT INTO shared_workflow ("workflowId", "projectId", "role")
                        VALUES ($1, $2, $3)
                    ''', workflow['id'], closest_project['id'], 'workflow:owner')
                    
                    print(f"✅ Fixed: {workflow['name']} → {closest_project['name']}")
                    fixed_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to fix {workflow['name']}: {e}")
            else:
                print(f"⚠️  No matching project found for {workflow['name']}")
        
        print(f"\n🎉 Fixed {fixed_count} orphaned workflows!")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔧 Template Workflow Orphan Fixer")
    print("=" * 50)
    
    asyncio.run(fix_orphaned_workflows())