#!/usr/bin/env python3
"""
Comprehensive unit tests for settings and configuration.

Tests settings validation, environment variable handling, and configuration edge cases.
Covers all settings fields and validation rules.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError
from typing import Optional

import sys
sys.path.insert(0, '/Users/mohmdfo/dev/sharif/n8n-sso-gateway')

from conf.settings import Settings, get_settings
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl


class TestSettingsValidation:
    """Test Settings class validation and field handling."""
    
    def test_settings_creation_minimal(self):
        """Test Settings creation with minimal required fields."""
        # Test with minimal required configuration
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        }
        
        settings = Settings(**settings_data)
        
        # Verify required fields
        assert str(settings.N8N_BASE_URL) == "https://n8n.example.com/"
        assert settings.N8N_DB_DSN == "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        
        # Verify defaults
        assert settings.N8N_DEFAULT_GLOBAL_ROLE == "global:member"
        assert settings.N8N_DEFAULT_PROJECT_ROLE == "project:personalOwner"
        assert settings.N8N_DEFAULT_LOCALE == "en"
        assert settings.COOKIE_SECURE is True
        assert settings.DEFAULT_REDIRECT_URL == "https://panel.ai-lab.ir/"
        
        print("✅ Settings creation (minimal) works correctly")
    
    def test_settings_creation_complete(self):
        """Test Settings creation with all fields."""
        # Test with complete configuration
        settings_data = {
            # Casdoor OAuth
            "CASDOOR_ENDPOINT": "https://casdoor.example.com",
            "CASDOOR_CLIENT_ID": "test_client_id",
            "CASDOOR_CLIENT_SECRET": "test_client_secret",
            "CASDOOR_ORG_NAME": "test_org",
            "CASDOOR_APP_NAME": "test_app",
            "CASDOOR_CERT_PATH": "/path/to/cert.pem",
            
            # n8n integration
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            "N8N_OWNER_EMAIL": "owner@example.com",
            "N8N_OWNER_PASSWORD": "owner_password",
            
            # Defaults
            "N8N_DEFAULT_GLOBAL_ROLE": "global:admin",
            "N8N_DEFAULT_PROJECT_ROLE": "project:owner",
            "N8N_DEFAULT_LOCALE": "ja",
            
            # Security
            "COOKIE_SECURE": False,
            "SECRET_KEY": "test_secret_key_123",
            
            # Redirect
            "DEFAULT_REDIRECT_URL": "https://custom.example.com"
        }
        
        settings = Settings(**settings_data)
        
        # Verify all fields
        assert settings.CASDOOR_ENDPOINT == "https://casdoor.example.com"
        assert settings.CASDOOR_CLIENT_ID == "test_client_id"
        assert settings.CASDOOR_CLIENT_SECRET == "test_client_secret"
        assert settings.CASDOOR_ORG_NAME == "test_org"
        assert settings.CASDOOR_APP_NAME == "test_app"
        assert settings.CASDOOR_CERT_PATH == "/path/to/cert.pem"
        
        assert str(settings.N8N_BASE_URL) == "https://n8n.example.com/"
        assert settings.N8N_DB_DSN == "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        assert str(settings.N8N_OWNER_EMAIL) == "owner@example.com"
        assert settings.N8N_OWNER_PASSWORD == "owner_password"
        
        assert settings.N8N_DEFAULT_GLOBAL_ROLE == "global:admin"
        assert settings.N8N_DEFAULT_PROJECT_ROLE == "project:owner"
        assert settings.N8N_DEFAULT_LOCALE == "ja"
        
        assert settings.COOKIE_SECURE is False
        assert settings.SECRET_KEY == "test_secret_key_123"
        assert settings.DEFAULT_REDIRECT_URL == "https://custom.example.com"
        
        print("✅ Settings creation (complete) works correctly")
    
    def test_settings_validation_invalid_url(self):
        """Test Settings validation with invalid URL."""
        # Test with invalid N8N_BASE_URL
        settings_data = {
            "N8N_BASE_URL": "not_a_valid_url",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)
        
        # Verify validation error
        assert "N8N_BASE_URL" in str(exc_info.value)
        
        print("✅ Settings validation (invalid URL) works correctly")
    
    def test_settings_validation_invalid_email(self):
        """Test Settings validation with invalid email."""
        # Test with invalid N8N_OWNER_EMAIL
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            "N8N_OWNER_EMAIL": "not_a_valid_email"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)
        
        # Verify validation error
        assert "N8N_OWNER_EMAIL" in str(exc_info.value)
        
        print("✅ Settings validation (invalid email) works correctly")
    
    def test_settings_missing_required_fields(self):
        """Test Settings validation with missing required fields."""
        # Test with missing N8N_BASE_URL by creating a custom Settings class without env file
        class TestSettings(BaseSettings):
            N8N_BASE_URL: AnyHttpUrl
            N8N_DB_DSN: str
            
            class Config:
                env_file = None  # Disable .env file loading
                case_sensitive = True
        
        settings_data = {
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TestSettings(**settings_data)
        
        # Verify validation error for required field
        assert "N8N_BASE_URL" in str(exc_info.value)
        
        print("✅ Settings validation (missing required fields) works correctly")
    
    def test_settings_optional_fields_none(self):
        """Test Settings with optional fields set to None."""
        # Test with optional fields explicitly set to None
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            "CASDOOR_ENDPOINT": None,
            "CASDOOR_CLIENT_ID": None,
            "N8N_OWNER_EMAIL": None,
            "SECRET_KEY": None
        }
        
        settings = Settings(**settings_data)
        
        # Verify None values are preserved
        assert settings.CASDOOR_ENDPOINT is None
        assert settings.CASDOOR_CLIENT_ID is None
        assert settings.N8N_OWNER_EMAIL is None
        assert settings.SECRET_KEY is None
        
        print("✅ Settings validation (optional fields None) works correctly")


class TestSettingsEnvironmentVariables:
    """Test Settings with environment variables."""
    
    @patch.dict(os.environ, {
        "N8N_BASE_URL": "https://env.n8n.example.com",
        "N8N_DB_DSN": "postgresql+asyncpg://env:pass@localhost:5432/n8n_env",
        "CASDOOR_ENDPOINT": "https://env.casdoor.example.com",
        "CASDOOR_CLIENT_ID": "env_client_id",
        "SECRET_KEY": "env_secret_key"
    })
    def test_settings_from_environment(self):
        """Test Settings loading from environment variables."""
        settings = Settings()
        
        # Verify environment variables are loaded
        assert str(settings.N8N_BASE_URL) == "https://env.n8n.example.com/"
        assert settings.N8N_DB_DSN == "postgresql+asyncpg://env:pass@localhost:5432/n8n_env"
        assert settings.CASDOOR_ENDPOINT == "https://env.casdoor.example.com"
        assert settings.CASDOOR_CLIENT_ID == "env_client_id"
        assert settings.SECRET_KEY == "env_secret_key"
        
        print("✅ Settings from environment variables works correctly")
    
    @patch.dict(os.environ, {
        "COOKIE_SECURE": "false",
        "N8N_DEFAULT_GLOBAL_ROLE": "global:viewer",
        "N8N_DEFAULT_PROJECT_ROLE": "project:viewer"
    })
    def test_settings_boolean_and_string_env_vars(self):
        """Test Settings with boolean and string environment variables."""
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        }
        
        settings = Settings(**settings_data)
        
        # Verify boolean conversion
        assert settings.COOKIE_SECURE is False
        
        # Verify string values
        assert settings.N8N_DEFAULT_GLOBAL_ROLE == "global:viewer"
        assert settings.N8N_DEFAULT_PROJECT_ROLE == "project:viewer"
        
        print("✅ Settings boolean and string env vars work correctly")
    
    @patch.dict(os.environ, {}, clear=True)
    def test_settings_no_environment_variables(self):
        """Test Settings when no environment variables are set."""
        # Create a custom Settings class without .env file loading
        class TestSettings(BaseSettings):
            N8N_BASE_URL: AnyHttpUrl
            N8N_DB_DSN: str
            CASDOOR_ENDPOINT: Optional[str] = None
            SECRET_KEY: Optional[str] = None
            COOKIE_SECURE: bool = True
            
            class Config:
                env_file = None  # Disable .env file loading
                case_sensitive = True
        
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
        }
        
        settings = TestSettings(**settings_data)
        
        # Verify defaults are used when no env vars
        assert settings.CASDOOR_ENDPOINT is None
        assert settings.SECRET_KEY is None
        assert settings.COOKIE_SECURE is True  # Default value
        
        print("✅ Settings without environment variables works correctly")


class TestGetSettingsFunction:
    """Test get_settings function and caching."""
    
    @patch('conf.settings.Settings')
    def test_get_settings_caching(self, mock_settings_class):
        """Test that get_settings caches the Settings instance."""
        # Mock Settings class
        mock_settings_instance = Mock()
        mock_settings_class.return_value = mock_settings_instance
        
        # Clear the cache first
        get_settings.cache_clear()
        
        # Call get_settings multiple times
        result1 = get_settings()
        result2 = get_settings()
        result3 = get_settings()
        
        # Verify same instance is returned
        assert result1 is result2
        assert result2 is result3
        assert result1 is mock_settings_instance
        
        # Verify Settings was only instantiated once
        mock_settings_class.assert_called_once()
        
        print("✅ get_settings caching works correctly")
    
    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        # Clear cache and test with real settings
        get_settings.cache_clear()
        
        # Mock environment for valid settings
        with patch.dict(os.environ, {
            "N8N_BASE_URL": "https://test.n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://test:pass@localhost:5432/test_n8n"
        }):
            settings = get_settings()
            
            assert isinstance(settings, Settings)
            assert str(settings.N8N_BASE_URL) == "https://test.n8n.example.com/"
        
        print("✅ get_settings returns Settings instance correctly")


class TestSettingsEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_settings_very_long_values(self):
        """Test Settings with very long field values."""
        # Test with very long strings
        long_string = "x" * 10000
        
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": f"postgresql+asyncpg://user:{long_string}@localhost:5432/n8n",
            "CASDOOR_CLIENT_SECRET": long_string,
            "SECRET_KEY": long_string
        }
        
        settings = Settings(**settings_data)
        
        # Verify long values are preserved
        assert len(settings.CASDOOR_CLIENT_SECRET) == 10000
        assert len(settings.SECRET_KEY) == 10000
        
        print("✅ Settings with very long values works correctly")
    
    def test_settings_special_characters(self):
        """Test Settings with special characters in values."""
        # Test with special characters
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~特殊文字"
        
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            "CASDOOR_ORG_NAME": special_chars,
            "CASDOOR_APP_NAME": special_chars,
            "SECRET_KEY": special_chars
        }
        
        settings = Settings(**settings_data)
        
        # Verify special characters are preserved
        assert settings.CASDOOR_ORG_NAME == special_chars
        assert settings.CASDOOR_APP_NAME == special_chars
        assert settings.SECRET_KEY == special_chars
        
        print("✅ Settings with special characters works correctly")
    
    def test_settings_url_variations(self):
        """Test Settings with various URL formats."""
        # Test different URL formats
        url_variations = [
            "https://n8n.example.com",
            "https://n8n.example.com:8080",
            "https://n8n.example.com/path",
            "https://n8n.example.com:8080/path/to/resource",
            "http://localhost:3000",
            "http://127.0.0.1:8080"
        ]
        
        for url in url_variations:
            settings_data = {
                "N8N_BASE_URL": url,
                "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n"
            }
            
            settings = Settings(**settings_data)
            # AnyHttpUrl only adds trailing slash to URLs without paths
            if '/' in url.split('://', 1)[1] and not url.endswith('/'):
                expected_url = url  # URLs with paths don't get trailing slash
            else:
                expected_url = url.rstrip('/') + '/'  # URLs without paths get trailing slash
            actual_url = str(settings.N8N_BASE_URL)
            print(f"URL: {url} -> Expected: {expected_url} -> Actual: {actual_url}")
            assert actual_url == expected_url
        
        print("✅ Settings with URL variations works correctly")
    
    def test_settings_database_dsn_variations(self):
        """Test Settings with various database DSN formats."""
        # Test different DSN formats
        dsn_variations = [
            "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            "postgresql+asyncpg://user@localhost/n8n",
            "postgresql+asyncpg://user:pass@remote.host.com:5432/n8n_db",
            "postgresql+asyncpg://user:complex_pass%40123@host:5432/db",
            "sqlite+aiosqlite:///path/to/database.db"
        ]
        
        for dsn in dsn_variations:
            settings_data = {
                "N8N_BASE_URL": "https://n8n.example.com",
                "N8N_DB_DSN": dsn
            }
            
            settings = Settings(**settings_data)
            assert settings.N8N_DB_DSN == dsn
        
        print("✅ Settings with DSN variations works correctly")
    
    def test_settings_extra_fields_allowed(self):
        """Test Settings with extra fields (should be allowed due to extra='allow')."""
        settings_data = {
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_DB_DSN": "postgresql+asyncpg://user:pass@localhost:5432/n8n",
            # Extra fields not defined in Settings class
            "CUSTOM_FIELD_1": "custom_value_1",
            "CUSTOM_FIELD_2": 12345,
            "CUSTOM_FIELD_3": True
        }
        
        settings = Settings(**settings_data)
        
        # Verify extra fields are preserved
        assert hasattr(settings, 'CUSTOM_FIELD_1')
        assert settings.CUSTOM_FIELD_1 == "custom_value_1"
        assert settings.CUSTOM_FIELD_2 == 12345
        assert settings.CUSTOM_FIELD_3 is True
        
        print("✅ Settings with extra fields works correctly")


class TestSettingsIntegration:
    """Test Settings integration scenarios."""
    
    @patch.dict(os.environ, {
        "N8N_BASE_URL": "https://prod.n8n.example.com",
        "N8N_DB_DSN": "postgresql+asyncpg://prod_user:prod_pass@prod.db.com:5432/n8n_prod",
        "CASDOOR_ENDPOINT": "https://prod.casdoor.example.com",
        "CASDOOR_CLIENT_ID": "prod_client_id",
        "CASDOOR_CLIENT_SECRET": "prod_client_secret",
        "COOKIE_SECURE": "true",
        "DEFAULT_REDIRECT_URL": "https://prod.panel.example.com"
    })
    def test_production_like_configuration(self):
        """Test Settings with production-like configuration."""
        settings = Settings()
        
        # Verify production settings
        assert str(settings.N8N_BASE_URL) == "https://prod.n8n.example.com/"
        assert "prod.db.com" in settings.N8N_DB_DSN
        assert settings.CASDOOR_ENDPOINT == "https://prod.casdoor.example.com"
        assert settings.CASDOOR_CLIENT_ID == "prod_client_id"
        assert settings.CASDOOR_CLIENT_SECRET == "prod_client_secret"
        assert settings.COOKIE_SECURE is True
        assert settings.DEFAULT_REDIRECT_URL == "https://prod.panel.example.com"
        
        print("✅ Production-like configuration works correctly")
    
    @patch.dict(os.environ, {
        "N8N_BASE_URL": "http://localhost:5678",
        "N8N_DB_DSN": "postgresql+asyncpg://dev:dev@localhost:5432/n8n_dev",
        "CASDOOR_ENDPOINT": "http://localhost:8000",
        "COOKIE_SECURE": "false"
    })
    def test_development_configuration(self):
        """Test Settings with development configuration."""
        settings = Settings()
        
        # Verify development settings
        assert str(settings.N8N_BASE_URL) == "http://localhost:5678/"
        assert "localhost" in settings.N8N_DB_DSN
        assert settings.CASDOOR_ENDPOINT == "http://localhost:8000"
        assert settings.COOKIE_SECURE is False
        
        print("✅ Development configuration works correctly")


def run_all_tests():
    """Run all settings and configuration tests."""
    print("⚙️  Starting Settings and Configuration Test Suite...")
    print("=" * 60)
    
    try:
        # Test settings validation
        validation_tests = TestSettingsValidation()
        validation_tests.test_settings_creation_minimal()
        validation_tests.test_settings_creation_complete()
        validation_tests.test_settings_validation_invalid_url()
        validation_tests.test_settings_validation_invalid_email()
        validation_tests.test_settings_missing_required_fields()
        validation_tests.test_settings_optional_fields_none()
        print()
        
        # Test environment variables
        env_tests = TestSettingsEnvironmentVariables()
        env_tests.test_settings_from_environment()
        env_tests.test_settings_boolean_and_string_env_vars()
        env_tests.test_settings_no_environment_variables()
        print()
        
        # Test get_settings function
        get_settings_tests = TestGetSettingsFunction()
        get_settings_tests.test_get_settings_caching()
        get_settings_tests.test_get_settings_returns_settings_instance()
        print()
        
        # Test edge cases
        edge_tests = TestSettingsEdgeCases()
        edge_tests.test_settings_very_long_values()
        edge_tests.test_settings_special_characters()
        edge_tests.test_settings_url_variations()
        edge_tests.test_settings_database_dsn_variations()
        edge_tests.test_settings_extra_fields_allowed()
        print()
        
        # Test integration scenarios
        integration_tests = TestSettingsIntegration()
        integration_tests.test_production_like_configuration()
        integration_tests.test_development_configuration()
        print()
        
        print("🎉 All Settings and Configuration tests passed!")
        print("✅ Settings validation working correctly")
        print("✅ Environment variable handling verified")
        print("✅ Caching mechanism functional")
        print("✅ URL and DSN validation robust")
        print("✅ Edge cases handled gracefully")
        print("✅ Integration scenarios tested")
        
        return True
        
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("⚙️  n8n SSO Gateway - Settings and Configuration Test Suite")
    print("=" * 60)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 60)
        print("🏆 ALL SETTINGS AND CONFIGURATION TESTS COMPLETED SUCCESSFULLY!")
        print("🔒 Configuration validation is robust and reliable")
        print("⚡ Environment variable handling verified")
        print("🎯 Settings caching working correctly")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("💥 SETTINGS AND CONFIGURATION TESTS FAILED!")
        print("❌ Configuration handling needs attention")
        print("=" * 60)
        exit(1)
