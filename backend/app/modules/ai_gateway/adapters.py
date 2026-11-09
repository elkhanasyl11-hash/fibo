"""AI service JSON -> backend types, checked against the service's real schemas (ai/fibo_ai/schemas, D81).

Anything that does not match raises ContractError and the caller falls back to the builtin module with
degraded=["ai_contract_mismatch"]; nothing half-parsed reaches a card.

  incident analyze  IncidentAnalyzeResponse: card {level normal|attention|critical, confidence
                    low|medium|high, headline, findings[], possible_causes[{text, manual_page}],
                    actions_now[{text, manual_page}], clarifying_question, manual_pages[] (the AI's
                    verified citations), card_text (Telegram HTML: ignored, the backend renders plain
                    text)}, signals {audio_z, audio_level, photo_wear, safety_triggers[]}, degraded[].
                    There is NO transcript in the answer.
  risk predict      RiskResult: p_model_cal (only if coverage.used has "model"), factors[], model_version
  panel             PanelResponse: readings {spindle_rpm, spindle_load_pct, temp_c, runtime_h, ...},
                    per_field_confidence {field: low|medium|high}
  audio baseline    BaselineArtifact: machine_id, embedder_id, sha256, blob_path, ... (stored, sent back)
  manual status     ManualStatusResponse: status indexing|ready|failed, pages_indexed, error
Mappings: level attention -> warning; confidence low/medium/high -> 0.33/0.66/0.9; tool wear
none|slight -> normal, moderate -> warning, severe -> critical; AI panel names -> backend fields.
"""

from dataclasses import dataclass, field

from app.db.base import IndexStatus
from app.modules.ai_gateway.errors import ContractError
from app.modules.vision.panel_ocr import PanelReadout, PanelValue

AI_LEVEL = {"normal": "normal", "attention": "warning", "critical": "critical"}
LEVEL_ORDER = ["normal", "warning", "critical"]
CONFIDENCE = {"low": 0.33, "medium": 0.66, "high": 0.9}
WEAR_TO_LEVEL = {"none": "normal", "slight": "normal", "moderate": "warning", "severe": "critical"}
PANEL_FIELDS = {"spindle_load_pct": "load_pct", "temp_c": "temperature_c", "runtime_h": "operating_hours"}
MAX_ITEM_CHARS = 300  # per cause / action / finding; keeps a card far below Telegram's 4096 characters


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _text(value, what: str) -> str:
    _need(isinstance(value, str) and bool(value.strip()), f"{what} is not a non-empty string")
    return value.strip()[:MAX_ITEM_CHARS]


def _level(value, what: str) -> str | None:
    if value is None:
        return None
    _need(value in AI_LEVEL, f"unknown {what} {value!r}")
    return AI_LEVEL[value]


@dataclass
class AIIncident:
    level: str
    verdict: str
    confidence: float
    causes: list[str]
    actions: list[str]
    findings: list[str]
    claimed_pages: set[int]
    citation_pages: set[int]
    safety_triggers: list[str]
    audio_z: float | None
    measured_level: str | None  # the AI's measured audio level / tool wear: a floor for the card
    clarifying_question: str | None
    degraded: list[str] = field(default_factory=list)

    def texts(self) -> list[str]:
        """Everything the AI wrote that may echo the operator's words: checked by the backend safety layer."""
        return [self.verdict, *self.findings, *self.causes, *self.actions]


def _items(entries, what: str) -> tuple[list[str], set[int]]:
    _need(isinstance(entries, list), f"{what} is not a list")
    texts, pages = [], set()
    for entry in entries:
        _need(isinstance(entry, dict), f"{what} item is not an object")
        texts.append(_text(entry.get("text"), f"{what} text"))
        page = entry.get("manual_page")
        _need(page is None or isinstance(page, int), f"{what} manual_page is not a number")
        if page is not None:
            pages.add(page)
    return texts, pages


def _measured_level(signals: dict) -> str | None:
    wear = signals.get("photo_wear")
    _need(wear is None or wear in WEAR_TO_LEVEL, f"unknown photo_wear {wear!r}")
    floors = [_level(signals.get("audio_level"), "audio level"), WEAR_TO_LEVEL.get(wear) if wear else None]
    return max((f for f in floors if f), key=LEVEL_ORDER.index, default=None)


def parse_incident(raw: dict) -> AIIncident:
    card, signals = raw.get("card"), raw.get("signals") or {}
    _need(isinstance(card, dict), "incident answer has no card")
    _need(isinstance(signals, dict), "incident signals is not an object")
    level = _level(card.get("level"), "card level")
    _need(level is not None, "card has no level")
    _need(card.get("confidence") in CONFIDENCE, f"unknown confidence {card.get('confidence')!r}")
    findings = [_text(f, "finding") for f in card.get("findings") or []]
    causes, cause_pages = _items(card.get("possible_causes") or [], "cause")
    actions, action_pages = _items(card.get("actions_now") or [], "action")
    citations = card.get("manual_pages") or []
    _need(all(isinstance(p, int) for p in citations), "manual_pages are not numbers")
    z = signals.get("audio_z")
    _need(z is None or isinstance(z, int | float), "audio_z is not a number")
    triggers = signals.get("safety_triggers") or []
    _need(isinstance(triggers, list), "safety_triggers is not a list")
    question = card.get("clarifying_question")
    return AIIncident(
        level=level,
        verdict=findings[0] if findings else _text(card.get("headline"), "headline"),
        confidence=CONFIDENCE[card["confidence"]],
        causes=causes,
        actions=actions,
        findings=findings[1:],
        claimed_pages=(cause_pages | action_pages) or set(citations),
        citation_pages=set(citations),
        safety_triggers=[str(t)[:50] for t in triggers],
        audio_z=float(z) if z is not None else None,
        measured_level=_measured_level(signals),
        clarifying_question=_text(question, "clarifying_question") if question else None,
        degraded=[str(d) for d in raw.get("degraded") or []],
    )


@dataclass
class AIRisk:
    probability: float | None  # None = the AI model gave no probability for these readings
    factors: list[dict]  # explanation entries of kind "shap" (title_ru from the AI's label_ru)
    model_version: str


def parse_risk(raw: dict) -> AIRisk:
    version = raw.get("model_version")
    _need(isinstance(version, str) and bool(version), "risk answer has no model_version")
    probability = raw.get("p_model_cal")
    coverage = raw.get("coverage") or {}
    _need(isinstance(coverage, dict), "risk coverage is not an object")
    if "model" not in (coverage.get("used") or []):
        probability = None  # the service sends 0.0 when its model is not loaded: "unknown", never "0 %"
    _need(
        probability is None or (isinstance(probability, int | float) and 0 <= probability <= 1),
        f"bad p_model_cal {probability!r}",
    )
    try:
        factors = [
            {
                "kind": "shap",
                "feature": str(f["name"]),
                "title_ru": str(f.get("label_ru") or f["name"]),
                "value": f.get("value"),
                "contribution": round(float(f["contribution"]), 4),
                "source": "ai",
            }
            for f in raw.get("factors") or []
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"bad risk factor: {exc}") from exc
    factors.sort(key=lambda f: abs(f["contribution"]), reverse=True)
    return AIRisk(float(probability) if probability is not None else None, factors, version)


def parse_panel(raw: dict) -> PanelReadout:
    readings, confidences = raw.get("readings"), raw.get("per_field_confidence") or {}
    _need(isinstance(readings, dict), "panel answer has no readings")
    _need(isinstance(confidences, dict), "per_field_confidence is not an object")
    values = []
    for name, value in readings.items():
        if value is None:  # not on the display: nothing to suggest
            continue
        _need(isinstance(value, int | float), f"panel value for {name} is not a number")
        word = confidences.get(name, "medium")
        _need(word in CONFIDENCE, f"bad confidence for {name}: {word!r}")
        values.append(
            PanelValue(field=PANEL_FIELDS.get(name, str(name)), value=value, confidence=CONFIDENCE[word])
        )
    return PanelReadout(values=values)


def parse_baseline(raw: dict) -> dict:
    keys = ("machine_id", "embedder_id", "sha256", "blob_path")
    _need(
        all(isinstance(raw.get(k), str) and raw.get(k) for k in keys),
        f"baseline artifact lacks one of {keys}",
    )
    return raw  # stored as is and sent back unchanged as baseline_ref


def parse_manual_status(raw: dict) -> tuple[IndexStatus, str | None, int | None]:
    status = raw.get("status")
    _need(status in {s.value for s in IndexStatus}, f"unknown manual status {status!r}")
    pages = raw.get("pages_indexed")
    return IndexStatus(status), raw.get("error") or None, pages if isinstance(pages, int) else None
