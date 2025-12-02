"""Direct n8n database operations for user/project/relation management."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4
import bcrypt
import secrets
import logging
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from sqlalchemy import text
from contextlib import asynccontextmanager

from conf.settings import get_settings
from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

PROJECT_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PROJECT_ID_LEN = 16

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def hash_password(raw: str) -> str:
    """Generate bcrypt hash with 10 rounds."""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=10)).decode()

def generate_random_password(length: int = 24) -> str:
    """Generate secure random password."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def gen_project_id() -> str:
    """Generate NanoID-style project ID."""
    return ''.join(secrets.choice(PROJECT_ID_ALPHABET) for _ in range(PROJECT_ID_LEN))

@dataclass
class CasdoorProfile:
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    casdoor_id: Optional[str] = None
    avatar_url: Optional[str] = None

@dataclass
class N8nUserRow:
    id: UUID
    email: str

@dataclass
class N8nProjectRow:
    id: str
    name: str

# Global engine (created once)
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.N8N_DB_DSN,
            echo=False,
        )
    return _engine

@asynccontextmanager
async def get_connection():
    """Get async database connection."""
    engine = get_engine()
    async with engine.begin() as conn:
        yield conn

async def ensure_user_project_binding(
    prof: CasdoorProfile,
    *,
    global_role: str = "global:member",  # Keep parameter for compatibility but don't use
    project_role: str = "project:personalOwner",
    now: datetime | None = None,
) -> Tuple[N8nUserRow, N8nProjectRow, Optional[str]]:
    """
    Upsert user, project, and relation in n8n database.
    
    Returns:
        (user_row, project_row, temp_password_if_new_else_None)
    """
    if now is None:
        now = now_utc()
    
    temp_password = None
    user_exists = False
    
    async with get_connection() as conn:
        # Set transaction isolation level to SERIALIZABLE
        await conn.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        
        # 1. Check if user exists
        user_result = await conn.execute(
            text('SELECT id, email FROM "user" WHERE email = :email FOR UPDATE'),
            {"email": prof.email}
        )
        user_row = user_result.fetchone()
        
        if user_row:
            user_exists = True
            user_id = user_row.id
            logger.info("Found existing user", extra={"email": prof.email, "user_id": str(user_id)})
        else:
            # Create new user
            user_id = uuid4()
            temp_password = generate_random_password()
            hashed_password = hash_password(temp_password)
            
            first_name = prof.first_name or prof.display_name or prof.email.split("@")[0]
            last_name = prof.last_name or ""
            
            await conn.execute(
                text('''
                    INSERT INTO "user" (
                        id, email, "firstName", "lastName", password, "roleSlug", disabled, "mfaEnabled",
                        settings, "personalizationAnswers", "createdAt", "updatedAt"
                    ) VALUES (
                        :id, :email, :firstName, :lastName, :password, :roleSlug, :disabled, :mfaEnabled,
                        :settings, :personalizationAnswers, :createdAt, :updatedAt
                    )
                '''),
                {
                    "id": user_id,
                    "email": prof.email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "password": hashed_password,
                    "roleSlug": global_role,  # Use the global_role parameter here
                    "disabled": False,
                    "mfaEnabled": False,
                    "settings": '{"userActivated": false}',
                    "personalizationAnswers": '{"version": "v4"}',
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
            logger.info("Created new user", extra={"email": prof.email, "user_id": str(user_id)})
        
        # 2. Check if project exists
        project_result = await conn.execute(
            text('SELECT id, name FROM project WHERE name = :name FOR UPDATE'),
            {"name": prof.email}
        )
        project_row = project_result.fetchone()
        
        if project_row:
            project_id = project_row.id
            logger.info("Found existing project", extra={"project_name": prof.email, "project_id": project_id})
        else:
            # Create new project
            project_id = gen_project_id()
            await conn.execute(
                text('''
                    INSERT INTO project (id, name, type, "createdAt", "updatedAt")
                    VALUES (:id, :name, :type, :createdAt, :updatedAt)
                '''),
                {
                    "id": project_id,
                    "name": prof.email,
                    "type": "personal",
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
            logger.info("Created new project", extra={"project_name": prof.email, "project_id": project_id})
        
        # 3. Upsert project relation
        await conn.execute(
            text('''
                INSERT INTO project_relation ("projectId", "userId", role, "createdAt", "updatedAt")
                VALUES (:projectId, :userId, :role, :createdAt, :updatedAt)
                ON CONFLICT ("projectId", "userId") DO NOTHING
            '''),
            {
                "projectId": project_id,
                "userId": user_id,
                "role": project_role,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        logger.info("Ensured project relation", extra={
            "project_id": project_id,
            "user_id": str(user_id),
            "role": project_role
        })
        
        # Create template workflow for new users
        if not user_exists:
            try:
                workflow_created = await create_template_workflow_for_user(
                    user_id=user_id,
                    project_id=project_id,
                    user_email=prof.email,
                    now=now
                )
                
                if workflow_created:
                    logger.info("Template workflow created for new user", extra={
                        "user_id": str(user_id),
                        "project_id": project_id,
                        "email": prof.email
                    })
                else:
                    logger.warning("Failed to create template workflow for new user", extra={
                        "user_id": str(user_id),
                        "project_id": project_id,
                        "email": prof.email
                    })
            except Exception as template_exc:
                logger.error("Exception while creating template workflow", extra={
                    "user_id": str(user_id),
                    "project_id": project_id,
                    "email": prof.email,
                    "error": str(template_exc)
                })
        
        return (
            N8nUserRow(id=user_id, email=prof.email),
            N8nProjectRow(id=project_id, name=prof.email),
            temp_password if not user_exists else None
        )

async def rotate_user_password(user_id: UUID, new_password: str) -> None:
    """Rotate password for existing user."""
    hashed_password = hash_password(new_password)
    now = now_utc()
    
    async with get_connection() as conn:
        await conn.execute(
            text('UPDATE "user" SET password = :password, "updatedAt" = :updatedAt WHERE id = :id'),
            {
                "password": hashed_password,
                "updatedAt": now,
                "id": user_id,
            }
        )
        logger.info("Rotated user password", extra={
            "user_id": str(user_id),
            "password_length": len(new_password),
            "hash_prefix": hashed_password[:10]
        })


async def get_user_by_email(email: str) -> N8nUserRow | None:
    """
    Find user by email in n8n database.
    
    Returns:
        N8nUserRow if found, None otherwise
    """
    async with get_connection() as conn:
        user_result = await conn.execute(
            text('SELECT id, email, password FROM "user" WHERE email = :email'),
            {"email": email}
        )
        user_row = user_result.fetchone()
        
        if user_row:
            logger.info("Found user by email", extra={
                "email": email, 
                "user_id": str(user_row.id)
            })
            # Create a user row object with the password field
            class UserWithPassword(N8nUserRow):
                def __init__(self, id, email, password=None):
                    super().__init__(id, email)
                    self.password = password
                    
            return UserWithPassword(id=user_row.id, email=user_row.email, password=user_row.password)
        
        logger.info("User not found by email", extra={"email": email})
        return None


async def invalidate_user_sessions_db(user_email: str) -> bool:
    """
    Invalidate all active sessions for a user by rotating their password.
    This forces all existing JWT tokens to become invalid.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        async with get_connection() as conn:
            # Generate a new random password to invalidate all existing sessions
            new_password = generate_random_password()
            new_password_hash = hash_password(new_password)
            
            # Update the user's password in the database
            result = await conn.execute(
                text('UPDATE "user" SET password = :password WHERE email = :email'),
                {"password": new_password_hash, "email": user_email}
            )
            
            if result.rowcount > 0:
                logger.info("User sessions invalidated via password rotation", extra={
                    "user_email": user_email,
                    "rows_updated": result.rowcount
                })
                return True
            else:
                logger.warning("No user found to invalidate sessions", extra={
                    "user_email": user_email
                })
                return False
                
    except Exception as exc:
        logger.error("Failed to invalidate user sessions in database", extra={
            "user_email": user_email,
            "error": str(exc)
        })
        return False


async def create_template_workflow_for_user(
    user_id: UUID, 
    project_id: str, 
    user_email: str,
    now: datetime | None = None
) -> bool:
    """
    Create a template workflow for a new user in the n8n database.
    
    Args:
        user_id: The user's UUID
        project_id: The project ID
        user_email: The user's email for personalization
        now: Current timestamp
    
    Returns:
        True if successful, False otherwise
    """
    from uuid import uuid4
    from apps.integrations.template_manager import get_template_manager
    
    if now is None:
        now = now_utc()
    
    try:
        # Get the template manager and default template
        template_manager = get_template_manager()
        template = template_manager.get_default_template()
        
        if not template:
            logger.warning("No default template available for new user", extra={
                "user_id": str(user_id),
                "user_email": user_email
            })
            return False
        
        # Prepare template data for this user
        workflow_data = template.prepare_for_user(user_email)
        
        if not workflow_data:
            logger.error("Template data is empty after preparation", extra={
                "template_name": template.name,
                "user_id": str(user_id),
                "user_email": user_email
            })
            return False
        
        # Generate new workflow ID and update metadata
        workflow_id = gen_project_id()  # Reuse the project ID generator
        
        async with get_connection() as conn:
            # First check if workflow_entity table exists and get its structure
            try:
                workflow_columns_result = await conn.execute(
                    text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'workflow_entity' 
                        AND table_schema = 'public'
                    """)
                )
                workflow_columns = [row[0] for row in workflow_columns_result.fetchall()]
                
                # Check if shared_workflow table exists
                relation_table_result = await conn.execute(
                    text("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_name IN ('shared_workflow', 'workflow_entity_relation') 
                        AND table_schema = 'public'
                    """)
                )
                relation_tables = [row[0] for row in relation_table_result.fetchall()]
                
            except Exception as schema_exc:
                logger.error("Failed to check workflow table schema", extra={
                    "user_id": str(user_id),
                    "error": str(schema_exc)
                })
                return False
            
            if not workflow_columns:
                logger.error("workflow_entity table not found", extra={
                    "user_id": str(user_id),
                    "user_email": user_email
                })
                return False
            
            # Prepare workflow data for workflow_entity table
            workflow_params = {
                "id": workflow_id,
                "name": workflow_data.get("name", "Template Workflow"),
                "active": False,  # Start inactive
                "nodes": json.dumps(workflow_data.get("nodes", [])),
                "connections": json.dumps(workflow_data.get("connections", {})),
                "settings": json.dumps(workflow_data.get("settings", {})),
                "staticData": json.dumps({}),
                "pinData": json.dumps(workflow_data.get("pinData", {})),
                "versionId": str(uuid4()),
                "triggerCount": 0,
                "createdAt": now,
                "updatedAt": now,
                "meta": json.dumps({}),
                "isArchived": False
            }
            
            # Insert the workflow into workflow_entity
            try:
                await conn.execute(
                    text('''
                        INSERT INTO workflow_entity (
                            id, name, active, nodes, connections, settings, "staticData",
                            "pinData", "versionId", "triggerCount", "createdAt", "updatedAt",
                            meta, "isArchived"
                        ) VALUES (
                            :id, :name, :active, :nodes, :connections, :settings, :staticData,
                            :pinData, :versionId, :triggerCount, :createdAt, :updatedAt,
                            :meta, :isArchived
                        )
                    '''),
                    workflow_params
                )
                
                logger.info("Workflow successfully inserted into workflow_entity", extra={
                    "workflow_id": workflow_id,
                    "workflow_name": workflow_params.get("name"),
                    "user_email": user_email
                })
                
            except Exception as workflow_insert_exc:
                logger.error("Failed to insert workflow into workflow_entity", extra={
                    "workflow_id": workflow_id,
                    "user_email": user_email,
                    "error": str(workflow_insert_exc),
                    "error_type": type(workflow_insert_exc).__name__,
                    "workflow_params_keys": list(workflow_params.keys())
                })
                # This is a critical failure - return False
                return False
            
            # Create workflow association using shared_workflow table
            if "shared_workflow" in relation_tables:
                try:
                    # Check if workflow is already shared first
                    existing_result = await conn.execute(
                        text('SELECT * FROM shared_workflow WHERE "workflowId" = :workflowId'),
                        {"workflowId": workflow_id}
                    )
                    existing_rows = existing_result.fetchall()
                    
                    if existing_rows:
                        logger.warning("Workflow sharing already exists", extra={
                            "workflow_id": workflow_id,
                            "existing_sharing_count": len(existing_rows)
                        })
                    else:
                        # Use simplified insert (let database handle timestamps)
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
                        
                        logger.info("Workflow shared with project successfully", extra={
                            "workflow_id": workflow_id,
                            "project_id": project_id,
                            "user_email": user_email,
                            "method": "simplified_insert"
                        })
                        
                except Exception as share_exc:
                    logger.error("Failed to share workflow with project", extra={
                        "user_id": str(user_id),
                        "workflow_id": workflow_id,
                        "project_id": project_id,
                        "user_email": user_email,
                        "error": str(share_exc),
                        "error_type": type(share_exc).__name__,
                        "workflow_created": True,
                        "error_details": repr(share_exc)
                    })
                    
                    # This is not critical - workflow exists, just not shared properly
                    # Log but don't fail the entire operation
            else:
                logger.warning("shared_workflow table not found, workflow created without project association", extra={
                    "user_id": str(user_id),
                    "workflow_id": workflow_id,
                    "project_id": project_id
                })
            
            logger.info("Template workflow created for user", extra={
                "user_id": str(user_id),
                "project_id": project_id,
                "workflow_id": workflow_id,
                "workflow_name": workflow_params.get("name"),
                "template_name": template.name,
                "user_email": user_email,
                "table_used": "workflow_entity",
                "relation_tables": relation_tables
            })
            
            return True
            
    except Exception as exc:
        logger.error("Failed to create template workflow for user", extra={
            "user_id": str(user_id),
            "project_id": project_id,
            "user_email": user_email,
            "error": str(exc)
        })
        return False
