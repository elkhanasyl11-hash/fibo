"""AI gateway (app/modules/ai_gateway): sidecar first, builtin fallback, input-error cards, health status.

All AI answers come from httpx.MockTransport; no network (R3). Each test sets FIBO_AI_PROVIDER itself,
so the file passes whether the suite runs with the builtin or the sidecar provider.
"""

import filecmp
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.core.errors import NotFoundError
from app.modules.ai_gateway import adapters, provider, status
from app.modules.ai_gateway.client import FiboAIClient, FiboAIError
from app.modules.ai_gateway.errors import AIRequestRejected, ContractError, classify, fails_incident
from app.modules.ai_gateway.ids import m_id, manual_id, ws_id
from app.modules.ai_gateway.messages import input_error_text
from app.modules.ai_gateway.paths import shared_path
from app.modules.assistant.llm import _sampling
from tests import ai_samples

REPO = Path(__file__).resolve().parents[2]
REQUEST = {"workshop_id": "ws-1", "machine_id": "m-1"}


def envelope(status_code: int, code: str, **details) -> httpx.Response:
    body = {"error": {"code": code, "message": code.lower(), "retriable": False, "details": details}}
    return httpx.Response(status_code, json=body)


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.fixture
def sidecar(monkeypatch):
    """Switch to the sidecar provider; `answer(handler)` sets what the AI service replies."""
    monkeypatch.setattr(settings, "ai_provider", "sidecar")
    calls: list[httpx.Request] = []

    def answer(handler):
        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        transport = httpx.MockTransport(recording)
        monkeypatch.setattr(
            provider,
            "make_client",
            lambda: FiboAIClient("http://ai:8001", transport=transport, retry_waits=()),
        )
        return calls

    return answer


async def builtin_card():
    return "builtin-card"


async def must_not_fall_back():
    pytest.fail("no builtin fallback expected here")


def test_backend_client_is_the_ai_client_copy():
    copy = REPO / "backend" / "app" / "modules" / "ai_gateway" / "client.py"
    assert filecmp.cmp(REPO / "ai" / "fibo_ai_client.py", copy, shallow=False)


@pytest.mark.parametrize(
    ("status_code", "code", "kind"),
    [
        (0, "UNREACHABLE", "unavailable"),
        (503, "LLM_UNAVAILABLE", "unavailable"),
        (500, "INTERNAL", "unavailable"),
        (422, "PHOTO_QUALITY_LOW", "input"),
        (422, "ASR_LOW_CONFIDENCE", "input"),
        (422, "AUDIO_SILENT", "input"),
        (409, "BASELINE_VERSION_MISMATCH", "recoverable"),
        (404, "MANUAL_NOT_INDEXED", "soft"),
        (409, "MACHINE_AMBIGUOUS", "bug"),
        (400, "VALIDATION_ERROR", "bug"),
    ],
)
def test_classify(status_code, code, kind):
    assert classify(FiboAIError(status_code, code, "", False, {})) == kind


def test_rejected_requests_fail_the_incident():
    assert fails_incident(FiboAIError(413, "FILE_TOO_LARGE", "", False, {}))
    assert not fails_incident(FiboAIError(409, "MACHINE_AMBIGUOUS", "", False, {}))


async def test_builtin_provider_never_calls_the_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "builtin")
    monkeypatch.setattr(provider, "make_client", lambda: pytest.fail("AI client must not be created"))
    outcome = await provider.analyze_incident(REQUEST, builtin_card)
    assert (outcome.source, outcome.value, outcome.degraded) == ("builtin", "builtin-card", [])


async def test_sidecar_answer_is_adapted(sidecar):
    calls = sidecar(lambda r: httpx.Response(200, json=ai_samples.incident()))
    outcome = await provider.analyze_incident(REQUEST, must_not_fall_back)
    assert outcome.source == "ai" and outcome.degraded == []
    assert outcome.value.level == "warning" and outcome.value.confidence == 0.66  # attention -> warning
    assert outcome.value.claimed_pages == {12, 99} and outcome.value.citation_pages == {12}
    assert outcome.value.verdict == "Износ подшипника шпинделя"
    assert outcome.value.actions == ["Снизить обороты", "Позвать механика"]
    assert calls[0].url.path == "/v1/incident/analyze"


@pytest.mark.parametrize(
    ("handler", "degraded"),
    [
        (unreachable, "ai_sidecar_unavailable"),
        (lambda r: envelope(503, "LLM_UNAVAILABLE"), "ai_sidecar_unavailable"),
        (lambda r: envelope(404, "MANUAL_NOT_INDEXED"), "ai_manual_not_indexed"),
        (lambda r: envelope(409, "MACHINE_AMBIGUOUS"), "ai_contract_mismatch"),
        (lambda r: envelope(409, "BASELINE_VERSION_MISMATCH"), "ai_baseline_mismatch"),
        (lambda r: httpx.Response(200, json={"unexpected": True}), "ai_contract_mismatch"),
        (lambda r: httpx.Response(200, text="not json"), "ai_contract_mismatch"),
        (
            lambda r: httpx.Response(401, json={"detail": "Invalid or missing service token"}),
            "ai_auth_failed",
        ),
    ],
)
async def test_sidecar_failures_fall_back_to_builtin(sidecar, handler, degraded):
    sidecar(handler)
    outcome = await provider.analyze_incident(REQUEST, builtin_card)
    assert (outcome.source, outcome.value, outcome.degraded) == ("builtin", "builtin-card", [degraded])


async def test_input_error_is_shown_not_replaced(sidecar):
    sidecar(lambda r: envelope(422, "ASR_LOW_CONFIDENCE"))
    outcome = await provider.analyze_incident(REQUEST, must_not_fall_back)
    assert outcome.source == "ai" and outcome.input_error.code == "ASR_LOW_CONFIDENCE"
    assert "Не удалось разобрать речь" in input_error_text(outcome.input_error, "ru")
    assert "Сөзді тану" in input_error_text(outcome.input_error, "kk")


def test_blurry_photo_uses_the_service_advice():
    error = FiboAIError(422, "PHOTO_QUALITY_LOW", "", False, {"retake_advice_kk": "Жарықты қосыңыз"})
    assert input_error_text(error, "kk") == "📷 Жарықты қосыңыз"
    assert "Переснимите" in input_error_text(error, "ru")  # no Russian advice -> fixed text


async def test_baseline_mismatch_retries_once_after_rebuild(sidecar):
    sidecar(lambda r: envelope(409, "BASELINE_VERSION_MISMATCH"))

    async def rebuilt(client):
        return ai_samples.incident()

    outcome = await provider.analyze_incident(REQUEST, must_not_fall_back, on_recoverable=rebuilt)
    assert outcome.source == "ai" and outcome.degraded == ["ai_baseline_rebuilt"]


async def test_rejected_request_raises(sidecar):
    sidecar(lambda r: envelope(400, "VALIDATION_ERROR"))
    with pytest.raises(AIRequestRejected, match="ai: VALIDATION_ERROR"):
        await provider.analyze_incident(REQUEST, must_not_fall_back)


async def test_other_wrappers_reach_their_endpoints(sidecar):
    answer = {**ai_samples.RISK, **ai_samples.PANEL, **ai_samples.MANUAL_STATUS}
    calls = sidecar(lambda r: httpx.Response(200, json=answer))
    await provider.predict_risk({"machine_id": "m-1", "readings": {}}, must_not_fall_back)
    await provider.read_panel({"file_path": "/app/data/media/p.jpg", "machine_id": "m-1"}, must_not_fall_back)
    await provider.manual_status("man-1", must_not_fall_back)
    assert [c.url.path for c in calls] == ["/v1/risk/predict", "/v1/vision/panel", "/v1/manuals/man-1/status"]


def test_parse_incident_rules():
    raw = ai_samples.incident(
        card={"level": "normal", "confidence": "high", "findings": [], "manual_pages": [12, 47]},
        signals={
            "audio_z": 7.1,
            "audio_level": "attention",
            "photo_wear": "severe",
            "safety_triggers": ["дым*"],
        },
        degraded=["llm_fallback"],
    )
    incident = adapters.parse_incident(raw)
    assert incident.level == "normal" and incident.measured_level == "critical"  # severe wear is a floor
    assert incident.verdict == ai_samples.CARD["headline"]  # no findings -> the headline
    assert incident.confidence == 0.9 and incident.audio_z == 7.1
    assert incident.citation_pages == {12, 47} and incident.safety_triggers == ["дым*"]
    assert incident.degraded == ["llm_fallback"]
    broken_answers = (
        ai_samples.incident(card={"level": "warning"}),  # the AI says "attention", never "warning"
        ai_samples.incident(card={"confidence": "very"}),
        ai_samples.incident(card={"possible_causes": [{"text": " "}]}),
        ai_samples.incident(card={"actions_now": ["plain string"]}),
        ai_samples.incident(signals={"photo_wear": "broken"}),
        {"text": "no card"},
    )
    for broken in broken_answers:
        with pytest.raises(ContractError):
            adapters.parse_incident(broken)


def test_parse_risk_panel_baseline_manual():
    risk = adapters.parse_risk(ai_samples.RISK)
    assert risk.probability == 0.42 and [f["feature"] for f in risk.factors] == [
        "spindle_load_pct",
        "tool_hours",
    ]
    assert risk.factors[0]["title_ru"] == "Нагрузка шпинделя" and risk.factors[0]["kind"] == "shap"
    assert adapters.parse_risk({**ai_samples.RISK, "p_model_cal": None}).probability is None
    no_model = {
        **ai_samples.RISK,
        "p_model_cal": 0.0,
        "coverage": {**ai_samples.RISK["coverage"], "used": []},
    }
    assert adapters.parse_risk(no_model).probability is None  # the AI's 0.0 without a model is not "0 %"
    panel = adapters.parse_panel(ai_samples.PANEL)
    assert [(v.field, v.value, v.confidence) for v in panel.values] == [
        ("spindle_rpm", 2400.0, 0.9),
        ("load_pct", 400.0, 0.33),
        ("operating_hours", 1200.0, 0.66),
    ]  # temp_c is null on the display -> not suggested
    assert adapters.parse_baseline(ai_samples.BASELINE) == ai_samples.BASELINE
    assert adapters.parse_manual_status(ai_samples.MANUAL_STATUS)[2] == 40
    broken = (
        (adapters.parse_risk, {**ai_samples.RISK, "p_model_cal": 2}),
        (adapters.parse_panel, {"readings": {"temp_c": "hot"}}),
        (adapters.parse_panel, {"readings": {"temp_c": 40}, "per_field_confidence": {"temp_c": 0.5}}),
        (adapters.parse_baseline, {"machine_id": "m-1", "embedder_id": "mfcc_baseline"}),
        (adapters.parse_manual_status, {"status": "done"}),
    )
    for parse, answer in broken:
        with pytest.raises(ContractError):
            parse(answer)


def test_ids_and_shared_paths():
    assert (ws_id(3), m_id(42), manual_id(7)) == ("ws-3", "m-42", "man-7")
    voice = settings.media_dir / "voice"
    voice.mkdir(parents=True, exist_ok=True)
    (voice / "a.ogg").write_bytes(b"x")
    assert shared_path("voice/a.ogg") == "/app/data/media/voice/a.ogg"
    for escape in ("../../test.db", "/etc/passwd", "voice/missing.ogg"):
        with pytest.raises(NotFoundError):
            shared_path(escape)


def test_reasoning_models_get_effort_not_temperature():
    assert _sampling("low") == {"reasoning_effort": "low"}
    assert _sampling("none") == {"reasoning_effort": "none"}
    assert _sampling("off") == {"temperature": 0}


@pytest.mark.parametrize(
    ("provider_name", "handler", "sidecar_state", "models"),
    [
        ("builtin", None, "disabled", None),
        ("sidecar", lambda r: httpx.Response(200, json={"risk": "lgbm-1"}), "ready", {"risk": "lgbm-1"}),
        ("sidecar", lambda r: httpx.Response(503), "unreachable", None),
        ("sidecar", unreachable, "unreachable", None),
    ],
)
async def test_health_reports_ai_status(client, monkeypatch, provider_name, handler, sidecar_state, models):
    monkeypatch.setattr(settings, "ai_provider", provider_name)
    monkeypatch.setattr(status, "_transport", httpx.MockTransport(handler) if handler else None)
    status.reset_cache()
    response = await client.get("/api/v1/health")
    assert response.status_code == 200  # the AI being down never fails health
    body = response.json()
    assert (body["ai_provider"], body["ai_sidecar"], body["ai_models"]) == (
        provider_name,
        sidecar_state,
        models,
    )
    status.reset_cache()


def test_sidecar_in_production_needs_an_ai_token():
    from app.core.config import Settings

    secure = {
        "_env_file": None,
        "env": "prod",
        "bot_shared_secret": "s" * 32,
        "dashboard_api_key": "d" * 32,
        "web_session_secret": "w" * 32,
    }
    # (dict keys, not `name=` literals, so the release secret scan does not match test dummies)
    with pytest.raises(ValueError, match="FIBO_AI_TOKEN"):
        Settings(**secure, ai_provider="sidecar")
    assert Settings(**secure, ai_provider="sidecar", ai_token="t" * 32).ai_provider == "sidecar"
