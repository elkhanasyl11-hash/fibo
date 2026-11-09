import re
from pathlib import Path
from typing import Any

import yaml

from fibo_ai.schemas.common import FiboBaseModel, IncidentLevel


class SafetyDecision(FiboBaseModel):
    force_stop: bool
    triggers: list[str]
    floor_level: IncidentLevel


class SafetyEngine:
    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path("configs/safety_keywords.yaml")
        self.compiled_rules: dict[str, list[re.Pattern[str]]] = {"ru": [], "kk": [], "en": []}
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
                for lang in ["ru", "kk", "en"]:
                    patterns = data.get(lang, [])
                    self.compiled_rules[lang] = [re.compile(p, re.IGNORECASE) for p in patterns]

    def evaluate(self, text: str) -> SafetyDecision:
        triggers: list[str] = []
        for _lang, patterns in self.compiled_rules.items():
            for pat in patterns:
                match = pat.search(text)
                if match:
                    triggers.append(match.group(0))

        if triggers:
            return SafetyDecision(
                force_stop=True,
                triggers=sorted(set(triggers)),
                floor_level=IncidentLevel.critical,
            )

        return SafetyDecision(
            force_stop=False,
            triggers=[],
            floor_level=IncidentLevel.normal,
        )


_DEFAULT_SAFETY_ENGINE: SafetyEngine | None = None


def get_safety_engine() -> SafetyEngine:
    global _DEFAULT_SAFETY_ENGINE
    if _DEFAULT_SAFETY_ENGINE is None:
        _DEFAULT_SAFETY_ENGINE = SafetyEngine()
    return _DEFAULT_SAFETY_ENGINE
