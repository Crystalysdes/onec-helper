from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    BOT_USERNAME: str = "oneshelperbot"
    ADMIN_TELEGRAM_ID: int = 5504548686
    WEBHOOK_URL: str = ""

    # Backend
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Database
    DATABASE_URL: str
    POSTGRES_USER: str = "onec_helper"
    POSTGRES_PASSWORD: str = "onec_helper_pass"
    POSTGRES_DB: str = "onec_helper_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # AI
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"

    # MiniApp
    MINIAPP_URL: str = "https://yourdomain.com"
    BACKEND_URL: str = "http://backend:8000"

    # Encryption
    ENCRYPTION_KEY: str = ""

    # YooKassa
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    SUBSCRIPTION_PRICE: float = 2499.0
    TRIAL_DAYS: int = 7

    # Environment
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
