from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    fibo_env: str = "development"
    fibo_port: int = 8001
    fibo_host: str = "0.0.0.0"
    fibo_data_dir: str = "artifacts"
    fibo_shared_dir: str = "/tmp/fibo_shared"
    log_level: str = "INFO"
    log_payloads: bool = False

    ai_stub_mode: bool = True
    ai_service_token: str | None = None

    llm_provider: str = "fake"
    llm_model: str = "gemini-1.5-flash"
    llm_vision_model: str = "gemini-1.5-flash"
    llm_fallback_model: str | None = None
    # Reasoning models (e.g. gpt-6-luna) reject temperature != 1; when set, reasoning_effort is sent instead.
    llm_reasoning_effort: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    asr_provider: str = "faster_whisper"
    whisper_model: str = "small"
    whisper_compute_type: str = "int8"

    model_version: str = "0.1.0-stub"
    config_version: str = "2026.11"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
