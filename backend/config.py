from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Telegram (legacy, kept for bot compatibility)
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = "oneshelperbot"
    ADMIN_TELEGRAM_ID: int = 5504548686
    WEBHOOK_URL: str = ""

    # Web auth
    ADMIN_EMAIL: str = ""

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
    ANTHROPIC_PROXY_URL: str = ""  # e.g. socks5://user:pass@host:port
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_FAST_MODEL: str = "anthropic/claude-3.5-haiku"
    OPENROUTER_VISION_MODEL: str = "anthropic/claude-3.5-haiku"
    OPENROUTER_INVOICE_MODEL: str = "anthropic/claude-3.5-sonnet"
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_INVOICE_MODEL: str = "claude-3-5-sonnet-20241022"

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
    LOGS_TOKEN: str = ""  # Secret token for /admin/app-logs endpoint (set in .env)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
