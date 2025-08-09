"""
Configuration management for walNUT.

This module uses Pydantic's BaseSettings to manage configuration
through environment variables. It provides a centralized and typed
way to handle application settings.
"""
import datetime
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="WALNUT_",
    )


# Global settings instance
settings = Settings()
