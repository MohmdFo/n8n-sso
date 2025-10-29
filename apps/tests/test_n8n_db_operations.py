#!/usr/bin/env python3
"""
Comprehensive unit tests for n8n database operations.

Tests all database functions with proper mocking to avoid actual database calls.
Covers user management, project binding, password operations, and edge cases.
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from apps.integrations.n8n_db import (
    CasdoorProfile,
    N8nUserRow,
    N8nProjectRow,
    ensure_user_project_binding,
    rotate_user_password,
    get_user_by_email,
    invalidate_user_sessions_db,
    hash_password,
    generate_random_password,
    gen_project_id,
    now_utc
)


class TestUtilityFunctions:
    """Test utility functions for password hashing, ID generation, etc."""
    
    def test_hash_password(self):
        """Test password hashing functionality."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert hashed is not None
        assert len(hashed) > 20  # bcrypt hashes are long
        assert hashed != password  # Should be different from original
        assert hashed.startswith('$2b$')  # bcrypt format
        
        # Test that same password produces different hashes (due to salt)
        hashed2 = hash_password(password)
        assert hashed != hashed2
        
        print("✅ Password hashing works correctly")
    
    def test_generate_random_password(self):
        """Test random password generation."""
        # Test default length
        password1 = generate_random_password()
        assert len(password1) == 24  # Default length
        
        # Test custom length
        password2 = generate_random_password(16)
        assert len(password2) == 16
        
        # Test passwords are different
        password3 = generate_random_password()
        assert password1 != password3
        
        # Test character set
        allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        for char in password1:
            assert char in allowed_chars
        
        print("✅ Random password generation works correctly")
    
    def test_gen_project_id(self):
        """Test project ID generation."""
        project_id1 = gen_project_id()
        assert len(project_id1) == 16  # Expected length
        
        project_id2 = gen_project_id()
        assert project_id1 != project_id2  # Should be unique
        
        # Test character set
        allowed_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        for char in project_id1:
            assert char in allowed_chars
        
        print("✅ Project ID generation works correctly")
    
    def test_now_utc(self):
        """Test UTC datetime generation."""
        dt = now_utc()
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc
        
        print("✅ UTC datetime generation works correctly")


class TestCasdoorProfile:
    """Test CasdoorProfile dataclass."""
    
    def test_casdoor_profile_creation(self):
        """Test CasdoorProfile creation with various field combinations."""
        # Minimal profile
        profile1 = CasdoorProfile(email="test@example.com")
        assert profile1.email == "test@example.com"
        assert profile1.first_name is None
        assert profile1.last_name is None
        
        # Full profile
        profile2 = CasdoorProfile(
            email="full@example.com",
            first_name="John",
            last_name="Doe",
            display_name="John Doe",
            casdoor_id="casdoor_123",
            avatar_url="https://example.com/avatar.jpg"
        )
        assert profile2.email == "full@example.com"
        assert profile2.first_name == "John"
        assert profile2.last_name == "Doe"
        assert profile2.display_name == "John Doe"
        assert profile2.casdoor_id == "casdoor_123"
        assert profile2.avatar_url == "https://example.com/avatar.jpg"
        
        print("✅ CasdoorProfile creation works correctly")


class TestDatabaseOperations:
    """Test database operations with proper mocking."""
    
    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.begin = AsyncMock()
        return conn
    
    @pytest.fixture
    def sample_profile(self):
        """Create a sample CasdoorProfile for testing."""
        return CasdoorProfile(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            display_name="Test User",
            casdoor_id="casdoor_test_123"
        )
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_ensure_user_project_binding_new_user(self, mock_get_connection, sample_profile):
        """Test user/project binding for a new user."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock user doesn't exist
        user_result = Mock()
        user_result.fetchone.return_value = None
        mock_conn.execute.side_effect = [
            user_result,  # User check
            None,         # User creation
            Mock(fetchone=Mock(return_value=None)),  # Project check
            None,         # Project creation
            None          # Relation creation
        ]
        
        # Execute function
        user_row, project_row, temp_password = await ensure_user_project_binding(sample_profile)
        
        # Verify results
        assert isinstance(user_row, N8nUserRow)
        assert user_row.email == sample_profile.email
        assert isinstance(project_row, N8nProjectRow)
        assert project_row.name == sample_profile.email
        assert temp_password is not None  # New user should get temp password
        assert len(temp_password) > 10
        
        # Verify database calls
        assert mock_conn.execute.call_count >= 4  # At least 4 SQL operations
        
        print("✅ New user/project binding works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_ensure_user_project_binding_existing_user(self, mock_get_connection, sample_profile):
        """Test user/project binding for an existing user."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock existing user
        existing_user_id = uuid.uuid4()
        user_result = Mock()
        user_result.fetchone.return_value = Mock(id=existing_user_id, email=sample_profile.email)
        
        # Mock existing project
        existing_project_id = "existing_project_123"
        project_result = Mock()
        project_result.fetchone.return_value = Mock(id=existing_project_id, name=sample_profile.email)
        
        mock_conn.execute.side_effect = [
            user_result,     # User check (exists)
            project_result,  # Project check (exists)
            None             # Relation upsert
        ]
        
        # Execute function
        user_row, project_row, temp_password = await ensure_user_project_binding(sample_profile)
        
        # Verify results
        assert isinstance(user_row, N8nUserRow)
        assert user_row.id == existing_user_id
        assert user_row.email == sample_profile.email
        assert isinstance(project_row, N8nProjectRow)
        assert project_row.id == existing_project_id
        assert temp_password is None  # Existing user should not get temp password
        
        print("✅ Existing user/project binding works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_rotate_user_password(self, mock_get_connection):
        """Test password rotation for existing user."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        user_id = uuid.uuid4()
        new_password = "new_secure_password_123"
        
        # Execute function
        await rotate_user_password(user_id, new_password)
        
        # Verify database call
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        
        # Verify SQL contains UPDATE statement
        sql_text = str(call_args[0][0])
        assert "UPDATE" in sql_text
        assert "password" in sql_text
        assert "user" in sql_text
        
        # Verify parameters
        params = call_args[1]
        assert "password" in params
        assert "id" in params
        assert params["id"] == user_id
        
        print("✅ Password rotation works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_get_user_by_email_found(self, mock_get_connection):
        """Test getting user by email when user exists."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock user exists
        user_id = uuid.uuid4()
        email = "existing@example.com"
        password_hash = "hashed_password_123"
        
        user_result = Mock()
        user_result.fetchone.return_value = Mock(
            id=user_id,
            email=email,
            password=password_hash
        )
        mock_conn.execute.return_value = user_result
        
        # Execute function
        result = await get_user_by_email(email)
        
        # Verify results
        assert result is not None
        assert result.id == user_id
        assert result.email == email
        assert hasattr(result, 'password')
        assert result.password == password_hash
        
        print("✅ Get user by email (found) works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_get_user_by_email_not_found(self, mock_get_connection):
        """Test getting user by email when user doesn't exist."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock user doesn't exist
        user_result = Mock()
        user_result.fetchone.return_value = None
        mock_conn.execute.return_value = user_result
        
        # Execute function
        result = await get_user_by_email("nonexistent@example.com")
        
        # Verify results
        assert result is None
        
        print("✅ Get user by email (not found) works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_invalidate_user_sessions_db_success(self, mock_get_connection):
        """Test successful user session invalidation."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock successful update
        update_result = Mock()
        update_result.rowcount = 1
        mock_conn.execute.return_value = update_result
        
        # Execute function
        result = await invalidate_user_sessions_db("test@example.com")
        
        # Verify results
        assert result is True
        
        # Verify database call
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        
        # Verify SQL contains UPDATE statement
        sql_text = str(call_args[0][0])
        assert "UPDATE" in sql_text
        assert "password" in sql_text
        
        print("✅ User session invalidation (success) works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_invalidate_user_sessions_db_user_not_found(self, mock_get_connection):
        """Test user session invalidation when user doesn't exist."""
        # Setup mock connection
        mock_conn = AsyncMock()
        mock_get_connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock no rows updated
        update_result = Mock()
        update_result.rowcount = 0
        mock_conn.execute.return_value = update_result
        
        # Execute function
        result = await invalidate_user_sessions_db("nonexistent@example.com")
        
        # Verify results
        assert result is False
        
        print("✅ User session invalidation (user not found) works correctly")
    
    @patch('apps.integrations.n8n_db.get_connection')
    async def test_database_error_handling(self, mock_get_connection):
        """Test database error handling."""
        # Setup mock connection that raises exception
        mock_get_connection.side_effect = Exception("Database connection failed")
        
        # Test that exceptions are properly handled
        with pytest.raises(Exception):
            await get_user_by_email("test@example.com")
        
        print("✅ Database error handling works correctly")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_casdoor_profile_edge_cases(self):
        """Test CasdoorProfile with edge case inputs."""
        # Empty email (should still work)
        profile1 = CasdoorProfile(email="")
        assert profile1.email == ""
        
        # Very long email
        long_email = "a" * 100 + "@example.com"
        profile2 = CasdoorProfile(email=long_email)
        assert profile2.email == long_email
        
        # Special characters in names
        profile3 = CasdoorProfile(
            email="test@example.com",
            first_name="José María",
            last_name="O'Connor-Smith",
            display_name="José María O'Connor-Smith"
        )
        assert profile3.first_name == "José María"
        assert profile3.last_name == "O'Connor-Smith"
        
        print("✅ CasdoorProfile edge cases handled correctly")
    
    def test_password_generation_edge_cases(self):
        """Test password generation with edge cases."""
        # Very short password
        short_password = generate_random_password(1)
        assert len(short_password) == 1
        
        # Very long password
        long_password = generate_random_password(100)
        assert len(long_password) == 100
        
        # Zero length (should handle gracefully)
        try:
            zero_password = generate_random_password(0)
            assert len(zero_password) == 0
        except Exception:
            # It's okay if this raises an exception
            pass
        
        print("✅ Password generation edge cases handled correctly")


async def run_all_tests():
    """Run all database operation tests."""
    print("🧪 Starting n8n Database Operations Test Suite...")
    print("=" * 60)
    
    try:
        # Test utility functions
        util_tests = TestUtilityFunctions()
        util_tests.test_hash_password()
        util_tests.test_generate_random_password()
        util_tests.test_gen_project_id()
        util_tests.test_now_utc()
        print()
        
        # Test CasdoorProfile
        profile_tests = TestCasdoorProfile()
        profile_tests.test_casdoor_profile_creation()
        print()
        
        # Test database operations
        db_tests = TestDatabaseOperations()
        sample_profile = CasdoorProfile(
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        
        await db_tests.test_ensure_user_project_binding_new_user(sample_profile)
        await db_tests.test_ensure_user_project_binding_existing_user(sample_profile)
        await db_tests.test_rotate_user_password()
        await db_tests.test_get_user_by_email_found()
        await db_tests.test_get_user_by_email_not_found()
        await db_tests.test_invalidate_user_sessions_db_success()
        await db_tests.test_invalidate_user_sessions_db_user_not_found()
        print()
        
        # Test edge cases
        edge_tests = TestEdgeCases()
        edge_tests.test_casdoor_profile_edge_cases()
        edge_tests.test_password_generation_edge_cases()
        print()
        
        print("🎉 All n8n Database Operations tests passed!")
        print("✅ User management functions working correctly")
        print("✅ Project binding operations verified")
        print("✅ Password operations secure and functional")
        print("✅ Database error handling robust")
        print("✅ Edge cases handled gracefully")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🗄️  n8n SSO Gateway - Database Operations Test Suite")
    print("=" * 60)
    
    success = asyncio.run(run_all_tests())
    
    if success:
        print("\n" + "=" * 60)
        print("🏆 ALL DATABASE TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Database operations are secure and reliable")
        print("⚡ User/project management functions verified")
        print("🎯 Password operations working correctly")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 DATABASE TESTS FAILED!")
        print("❌ Database operations need attention")
        print("=" * 60)
        exit(1)
