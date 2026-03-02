"""Настройки приложения — загрузка из .env."""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Config(BaseSettings):
    """Базовая конфигурация проекта."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_PROXY_HEIGHT: int = 480
    DEFAULT_TARGET_LUFS: float = -14.0
    MIN_START_OFFSET: float = 12.0
