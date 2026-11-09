"""Contract with the AI service's REAL schemas (ai/fibo_ai/schemas, D81): the sample answers the other AI
tests use, and the requests the backend builds, must validate against the service's own Pydantic models.
Only the schema modules are imported (they depend on pydantic alone); the service itself is not started.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

from app.db.base import utcnow
from app.models.machine import Machine
from app.modules.ai_gateway import adapters
from app.modules.ai_gateway.requests import machine_context, machine_readings
from app.modules.machine.feature_map import ReadingValues
from tests import ai_samples

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai"))
from fibo_ai.schemas import audio, incident, rag, risk, vision  # noqa: E402

MACHINE = Machine(
    id=7,
    workshop_id=3,
    name="ЧПУ-1",
    type="cnc_mill",
    criticality=2,
    avg_repair_hours=4.5,
    downtime_cost_per_hour_kzt=15000.5,
    batch_value_kzt=None,
    last_maintenance_at=utcnow() - timedelta(hours=100),
    maintenance_interval_hours=250.0,
)


@pytest.mark.parametrize(
    ("model", "sample"),
    [
        (incident.IncidentAnalyzeResponse, ai_samples.incident()),
        (risk.RiskResult, ai_samples.RISK),
        (vision.PanelResponse, ai_samples.PANEL),
        (audio.BaselineArtifact, ai_samples.BASELINE),
        (rag.ManualStatusResponse, ai_samples.MANUAL_STATUS),
    ],
)
def test_samples_are_real_ai_answers(model, sample):
    model.model_validate(sample)


def test_schema_examples_parse_in_the_backend():
    """The service's own documented example answer goes through the backend adapter."""
    example = incident.IncidentAnalyzeResponse.model_config["json_schema_extra"]["example"]
    parsed = adapters.parse_incident(example)
    assert parsed.level == "critical" and parsed.citation_pages == {47}
    assert parsed.safety_triggers == ["гар*"] and parsed.measured_level == "critical"


def test_backend_requests_are_valid_ai_requests():
    context = machine_context(MACHINE)
    assert context["criticality"] == "medium" and context["cost_per_hour_kzt"] == 15000
    incident.IncidentAnalyzeRequest.model_validate(
        {
            "workshop_id": "ws-3",
            "machine_id": "m-7",
            "profile": "metalworking",
            "lang": "kk",
            "text": "шум",
            "context": context,
            "catalog_machines": ["ЧПУ-1", "ЧПУ-2"],
            "baseline_ref": ai_samples.BASELINE,
            "voice_file_path": "/app/data/media/voice/a.ogg",
        }
    )
    latest = ReadingValues(
        recorded_at=utcnow(), spindle_rpm=1500, load_pct=60, temperature_c=41, operating_hours=900
    )
    readings = machine_readings(latest, 120.0, 24.85)
    risk.RiskRequest.model_validate(
        {"machine_id": "m-7", "profile": "metalworking", "readings": readings, "context": context}
    )
    vision.PanelRequest.model_validate(
        {"file_path": "/app/data/media/p.jpg", "machine_id": "m-7", "workshop_id": "ws-3"}
    )
    audio.BaselineCreateRequest.model_validate(
        {"machine_id": "m-7", "file_paths": ["/app/data/media/a.wav"] * 3, "embedder_id": "mfcc_baseline"}
    )
    rag.ManualIndexRequest.model_validate(
        {"manual_id": "man-1", "machine_id": "m-7", "file_path": "/app/data/media/m.pdf", "language": "ru"}
    )
