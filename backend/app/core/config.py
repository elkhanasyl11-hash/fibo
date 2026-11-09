"""Application settings, read from environment variables (prefix FIBO_) and .env files.

Why: no secrets or environment-specific values in code. Every value has a safe default for local
development in mock mode, so `uvicorn app.main:app` works without any configuration.

.env lookup: the repository root (`../.env` when running from backend/) and then `backend/.env`;
a value in the later file wins. Real environment variables always win over both files.
"""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BOT_SECRET = "change-me"
MIN_SECRET_LENGTH = 24


class Settings(BaseSettings):
    # env_ignore_empty: `FIBO_DASHBOARD_API_KEY=` (empty) means "use the default" (None), not "".
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_prefix="FIBO_", extra="ignore", env_ignore_empty=True
    )

    env: Literal["dev", "prod", "test"] = "dev"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./data/sqlite/fibo.db"
    data_dir: Path = Path("./data")
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    ai_mode: Literal["mock", "live"] = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "set-in-env"
    llm_vision_model: str = "set-in-env"
    llm_timeout_s: float = 45.0
    speech_backend: Literal["api", "local"] = "api"
    whisper_model: str = "set-in-env"
    # "auto" leaves sampling/reasoning to the provider for broad API compatibility.
    # "off" = a classic chat model: no reasoning_effort, temperature 0 instead.
    llm_reasoning_effort: Literal["auto", "off", "none", "minimal", "low", "medium", "high"] = "auto"
    ffmpeg_binary: str = "ffmpeg"  # if not found, OGG/WAV/MP3 are decoded with libsndfile instead

    bot_shared_secret: str = DEFAULT_BOT_SECRET  # header X-Fibo-Bot-Token
    dashboard_api_key: str | None = None  # header X-Fibo-Api-Key; None = disabled in dev
    # Signs web sign-in tokens (HMAC-SHA256). In dev an unset secret is persisted in data/web-session.key.
    # Prod refuses to start without an explicit secret of >= 24 characters.
    web_session_secret: str | None = None
    web_session_hours: int = 24 * 14
    # Public username of the Telegram bot (without @). The web sign-up shows a t.me deep link with it.
    telegram_bot_username: str | None = None

    # AI service (sidecar). "builtin" = only the backend's own modules (default; tests, no AI container).
    ai_provider: Literal["sidecar", "builtin"] = "builtin"
    ai_url: str = "http://ai:8001"
    ai_token: str | None = None  # sent as Authorization: Bearer; must match the service AI_SERVICE_TOKEN
    ai_timeout_s: float = 3.0  # health probe only; request timeouts are per endpoint in the client
    ai_shared_dir: Path = Path("/app/data/media")  # where the AI container sees the media volume
    model_cache_dir: Path | None = None  # default: <data_dir>/models
    max_upload_mb: int = 20
    audio_z_warning: float = 2.0  # audio_z >= this -> warning (see ml/eval_audio_mimii.py)
    audio_z_critical: float = 3.0  # audio_z > this -> critical
    embedding_backend: Literal["e5", "hash"] = "e5"  # hash = offline word-hash vectors (tests)
    embedding_model_repo: str = "intfloat/multilingual-e5-small"
    embedding_model_file: str = "onnx/model_qint8_avx512_vnni.onnx"
    rag_min_similarity: float = 0.83  # e5 cosine similarity below this = "not found in the manual"
    photo_min_sharpness: float = 60.0  # variance of the Laplacian below this = blurry
    photo_min_brightness: float = 40.0  # mean grey level 0..255 below this = too dark
    photo_max_brightness: float = 225.0  # above this = overexposed
    risk_model_dir: Path = Path("./ml/artifacts")
    risk_recompute_minutes: int = 60  # periodic risk recompute of every machine; 0 = off
    # Notifications to owners/masters about critical incidents go straight to the Telegram Bot API
    # with the bot's own token (same variable the bot reads). None = notifications off.
    telegram_bot_token: str | None = None
    web_base_url: str = "http://localhost:5173"  # links to the dashboard in notifications

    def insecure_reasons(self) -> list[str]:
        """Why this configuration must not face the internet (empty list = fine)."""
        reasons = []
        if self.bot_shared_secret == DEFAULT_BOT_SECRET or len(self.bot_shared_secret) < MIN_SECRET_LENGTH:
            reasons.append(
                f"FIBO_BOT_SHARED_SECRET is the default or shorter than {MIN_SECRET_LENGTH} characters"
            )
        if not self.dashboard_api_key:
            reasons.append("FIBO_DASHBOARD_API_KEY is empty, so the dashboard API has no key check")
        if not self.web_session_secret or len(self.web_session_secret) < MIN_SECRET_LENGTH:
            reasons.append(f"FIBO_WEB_SESSION_SECRET is empty or shorter than {MIN_SECRET_LENGTH} characters")
        if self.ai_provider == "sidecar" and (not self.ai_token or len(self.ai_token) < MIN_SECRET_LENGTH):
            reasons.append(f"FIBO_AI_TOKEN is empty or shorter than {MIN_SECRET_LENGTH} characters (sidecar)")
        return reasons

    @model_validator(mode="after")
    def refuse_insecure_production(self) -> "Settings":
        """In prod the app refuses to start with a guessable secret; dev only logs a warning (main.py)."""
        if self.env == "prod" and self.insecure_reasons():
            raise ValueError("insecure production settings: " + "; ".join(self.insecure_reasons()))
        return self

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def models_dir(self) -> Path:
        """Downloaded AI models. Docker images use a separate folder (outside the data volume)."""
        return self.model_cache_dir or self.data_dir / "models"


settings = Settings()
