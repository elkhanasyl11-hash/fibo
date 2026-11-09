"""Bot settings from environment variables / .env (same FIBO_ prefix as the backend)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_prefix="FIBO_", extra="ignore", env_ignore_empty=True
    )

    telegram_bot_token: str = ""  # from @BotFather; required to start the bot
    api_url: str = "http://localhost:8000/api/v1"
    bot_shared_secret: str = "change-me"  # must equal the backend's FIBO_BOT_SHARED_SECRET
    api_timeout_s: float = 30.0
    log_level: str = "INFO"


settings = BotSettings()
