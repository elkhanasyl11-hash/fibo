""".env.example must stay a valid configuration that runs in dev/mock mode."""

import re
from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_env_example_parses_to_safe_dev_defaults(monkeypatch):
    for name in ("FIBO_DASHBOARD_API_KEY", "FIBO_AI_MODE", "FIBO_ENV", "FIBO_DATABASE_URL", "FIBO_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.ai_mode == "mock"
    assert settings.dashboard_api_key is None  # empty value -> check disabled, not ""
    assert settings.llm_api_key is None
    assert settings.cors_origins == ["http://localhost:5173", "http://localhost:3000"]
    assert settings.llm_timeout_s == 45
    assert settings.database_url.startswith("sqlite+aiosqlite:///")


def test_every_setting_is_documented_in_env_example():
    documented = set(re.findall(r"^FIBO_(\w+)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.MULTILINE))
    missing = {name.upper() for name in Settings.model_fields} - documented
    assert not missing, f"add to .env.example: {sorted(missing)}"
