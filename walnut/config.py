"""
Configuration management for walNUT.

This module uses Pydantic's BaseSettings to manage configuration
through environment variables. It provides a centralized and typed
way to handle application settings.
"""
import datetime
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    These settings are loaded from environment variables.
    """

    # NUT Server Configuration
    NUT_HOST: str = "localhost"
    NUT_PORT: int = 3493
    NUT_USERNAME: str | None = None
    NUT_PASSWORD: str | None = None
    NUT_ENABLED: bool = True

    # Polling configuration
    POLL_INTERVAL: int = 5  # seconds
    HEARTBEAT_TIMEOUT: int = 30  # seconds

    # Data retention
    DATA_RETENTION_HOURS: int = 24

    # Authentication
    JWT_SECRET: str
    ACCESS_TTL: datetime.timedelta = datetime.timedelta(minutes=15)
    REFRESH_TTL: datetime.timedelta = datetime.timedelta(days=7)
    BCRYPT_WORK_FACTOR: int = 12
    COOKIE_NAME_ACCESS: str = "walnut_access"
    COOKIE_NAME_REFRESH: str = "walnut_refresh"
    SECURE_COOKIES: bool = True
    ALLOWED_ORIGINS: list[str] = []
    SIGNUP_ENABLED: bool = False
    TESTING_MODE: bool = False

    # OIDC SSO Configuration
    OIDC_ENABLED: bool = False
    OIDC_PROVIDER_NAME: str = "google"  # or "azure", "okta", etc.
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    OIDC_DISCOVERY_URL: str | None = None
    OIDC_ADMIN_ROLES: list[str] = []
    OIDC_VIEWER_ROLES: list[str] = []
    DB_PATH: str | None = None
    
    # Feature Flags
    POLICY_V1_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="WALNUT_",
    )


# Global settings instance with user-friendly error handling
try:
    settings = Settings()
except Exception as e:
    # Provide user-friendly error messages for missing environment variables
    if "JWT_SECRET" in str(e) and "Field required" in str(e):
        print(f"Environment Configuration Error")
        print(f"Missing required environment variable: WALNUT_JWT_SECRET")
        print(f"Please set the JWT signing secret (minimum 32 characters):")
        print(f"  export WALNUT_JWT_SECRET=\"your_32_character_jwt_secret_here\"")
        import sys
        sys.exit(1)
    else:
        # Re-raise other validation errors
        raise

def get_master_key() -> str:
    """
    Retrieve the database master key from environment or Docker secrets.

    Returns:
        str: The master key for database encryption

    Raises:
        ValueError: If no master key is found or key is invalid
    """
    # Try Docker secrets first
    secrets_path = Path("/run/secrets/walnut_db_key")
    if secrets_path.exists():
        try:
            key = secrets_path.read_text().strip()
            if key and len(key) >= 32:  # Minimum 32 chars for AES-256
                return key
        except (OSError, IOError):
            pass

    # Fall back to environment variable
    key = os.getenv("WALNUT_DB_KEY")
    if key and len(key) >= 32:
        return key

    # Development fallback (warn about security)
    dev_key = os.getenv("WALNUT_DB_KEY_DEV")
    if dev_key:
        return dev_key

    raise ValueError(
        "No valid master key found. Set WALNUT_DB_KEY environment variable "
        "or mount key as Docker secret at /run/secrets/walnut_db_key. "
        "Key must be at least 32 characters long."
    )
