from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class BotSettings(BaseSettings):
    BOT_TOKEN: str
    BOT_USERNAME: str = "oneshelperbot"
    ADMIN_TELEGRAM_ID: int = 5504548686
    BACKEND_URL: str = "http://backend:8000"
    MINIAPP_URL: str = "https://yourdomain.com"
    REDIS_URL: str = "redis://redis:6379/0"
    ENVIRONMENT: str = "production"

    class Config:
        env_file = str(_ENV_FILE)
        extra = "ignore"


settings = BotSettings()
