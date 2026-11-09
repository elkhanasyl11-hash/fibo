from pathlib import Path
from typing import Any

import yaml

from fibo_ai.schemas.common import Usage


def load_pricing(config_path: Path | None = None) -> dict[str, float]:
    if config_path is None:
        config_path = Path("configs/pricing.yaml")
    if not config_path.exists():
        return {
            "asr_per_minute": 0.006,
            "llm_input_per_million_tokens": 0.15,
            "llm_output_per_million_tokens": 0.60,
            "vision_call_per_image": 0.0025,
            "embed_per_million_tokens": 0.02,
        }
    with open(config_path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    rates = data.get("rates", {})
    return {
        "asr_per_minute": float(rates.get("asr_per_minute", 0.006)),
        "llm_input_per_million_tokens": float(rates.get("llm_input_per_million_tokens", 0.15)),
        "llm_output_per_million_tokens": float(rates.get("llm_output_per_million_tokens", 0.60)),
        "vision_call_per_image": float(rates.get("vision_call_per_image", 0.0025)),
        "embed_per_million_tokens": float(rates.get("embed_per_million_tokens", 0.02)),
    }


def compute_cost_usd(usage: Usage, rates: dict[str, float] | None = None) -> float:
    if rates is None:
        rates = load_pricing()
    cost = 0.0
    cost += (usage.asr_seconds / 60.0) * rates.get("asr_per_minute", 0.0)
    cost += (usage.llm_input_tokens / 1_000_000.0) * rates.get("llm_input_per_million_tokens", 0.0)
    cost += (usage.llm_output_tokens / 1_000_000.0) * rates.get("llm_output_per_million_tokens", 0.0)
    cost += usage.vision_calls * rates.get("vision_call_per_image", 0.0)
    cost += (usage.embed_calls / 1_000_000.0) * rates.get("embed_per_million_tokens", 0.0)
    return round(cost, 6)
