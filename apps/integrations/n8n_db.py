"""Direct n8n database operations for user/project/relation management."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4
import bcrypt
import secrets
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from sqlalchemy import text
from contextlib import asynccontextmanager

from conf.settings import get_settings

logger = logging.getLogger(__name__)

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
    global_role: str = "global:member",
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
                        id, email, "firstName", "lastName", password, role, 
                        settings, "personalizationAnswers", "createdAt", "updatedAt"
                    ) VALUES (
                        :id, :email, :firstName, :lastName, :password, :role,
                        :settings, :personalizationAnswers, :createdAt, :updatedAt
                    )
                '''),
                {
                    "id": user_id,
                    "email": prof.email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "password": hashed_password,
                    "role": global_role,
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
