import asyncio
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fibo_ai.assistant.repository import DataRepository, FakeRepository
from fibo_ai.assistant.service import AssistantService
from fibo_ai.audio.baseline import create_baseline
from fibo_ai.audio.embedder import AudioEmbedder, get_embedder
from fibo_ai.audio.io import load_audio, resolve_audio_path
from fibo_ai.audio.router import route_recording
from fibo_ai.audio.scorer import analyze_machine_audio
from fibo_ai.core.errors import FiboError
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.core.llm.fake import FakeLLM
from fibo_ai.core.llm.openai_compat import OpenAICompatClient
from fibo_ai.incident.service import IncidentService
from fibo_ai.rag.service import RAGService
from fibo_ai.risk.anomaly import ReadingAnomalyDetector
from fibo_ai.risk.model import RiskPredictor
from fibo_ai.risk.whatif import simulate_what_if
from fibo_ai.schemas.audio import (
    AudioAnalysis,
    AudioRouteRequest,
    AudioRouteResponse,
    BaselineArtifact,
    BaselineCreateRequest,
)
from fibo_ai.schemas.common import Usage
from fibo_ai.schemas.meta import (
    HealthResponse,
    ModelMetaInfo,
    ModelsMetaResponse,
    ReadyResponse,
)
from fibo_ai.schemas.risk import (
    AnomalyRequest,
    AnomalyResponse,
    AnomalySummary,
    RiskRankItem,
    RiskRankRequest,
    RiskRankResponse,
    RiskRequest,
    RiskResult,
    WhatIfRequest,
    WhatIfResult,
)
from fibo_ai.settings import Settings, get_settings
from fibo_ai.speech.asr import ASRProvider, FakeASR
from fibo_ai.speech.service import SpeechService
from fibo_ai.vision.service import VisionService


class RiskService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.predictor = RiskPredictor(settings)
        self.anomaly_detector = ReadingAnomalyDetector()

    async def predict(self, req: RiskRequest) -> RiskResult:
        is_anom, score, scope, top_feats = self.anomaly_detector.assess_reading(
            machine_id=req.machine_id,
            latest=req.readings,
            rated_rpm=req.context.rated_rpm or 4000.0,
        )
        anomaly_summary = AnomalySummary(
            is_anomaly=is_anom,
            score=score,
            scope=scope,
            top_features=top_feats,
        )
        return self.predictor.predict(req, anomaly_summary=anomaly_summary)

    async def rank(self, req: RiskRankRequest) -> RiskRankResponse:
        req_id = f"rank-{uuid.uuid4().hex[:8]}"
        items: list[RiskRankItem] = []
        for m in req.machines:
            res = await self.predict(m)
            items.append(
                RiskRankItem(
                    machine_id=m.machine_id,
                    priority_kzt=res.priority_kzt,
                    risk_index=res.risk_index,
                    risk_band=res.risk_band,
                    criticality=m.context.criticality,
                    expected_repair_hours=m.context.expected_repair_hours,
                    top_factors=res.factors[:3],
                )
            )
        items.sort(key=lambda x: x.priority_kzt, reverse=True)
        return RiskRankResponse(
            request_id=req_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            ranked_machines=items,
            usage=Usage(est_cost_usd=0.0001),
        )

    async def what_if(self, req: WhatIfRequest) -> WhatIfResult:
        return await simulate_what_if(req, self.predict)

    async def anomaly(self, req: AnomalyRequest) -> AnomalyResponse:
        req_id = f"anom-{uuid.uuid4().hex[:8]}"
        is_anom, score, scope, top_feats = self.anomaly_detector.assess_reading(
            machine_id=req.machine_id,
            latest=req.latest,
            history=req.history,
        )
        return AnomalyResponse(
            request_id=req_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            machine_id=req.machine_id,
            is_anomaly=is_anom,
            score=score,
            scope=scope,
            top_features=top_feats,
            usage=Usage(est_cost_usd=0.00002),
        )


class AudioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embedders: dict[str, AudioEmbedder] = {}
        self._embedder_lock = threading.Lock()

    def _embedder(self, embedder_id: str) -> tuple[AudioEmbedder, list[str]]:
        with self._embedder_lock:
            if embedder_id in self._embedders:
                return self._embedders[embedder_id], []
            degraded: list[str] = []
            try:
                embedder = get_embedder(embedder_id)
            except Exception:
                embedder = get_embedder("mfcc_baseline")
                degraded.append(f"{embedder_id}_unavailable_mfcc_fallback")
            self._embedders[embedder_id] = embedder
            return embedder, degraded

    def _shared_path(self, path: str) -> Path:
        try:
            return resolve_audio_path(path, Path(self.settings.fibo_shared_dir))
        except FileNotFoundError as exc:
            raise FiboError("FILE_NOT_FOUND", "Audio file was not found in FIBO_SHARED_DIR", 404) from exc
        except ValueError as exc:
            raise FiboError("INVALID_FILE_PATH", str(exc), 400) from exc

    @staticmethod
    def _map_audio_error(exc: Exception) -> FiboError:
        code = str(exc)
        if code.startswith("FILE_TOO_LARGE"):
            return FiboError("FILE_TOO_LARGE", "Audio file exceeds 15 MB", 413)
        if code == "UNSUPPORTED_MEDIA":
            return FiboError("UNSUPPORTED_MEDIA", "Could not decode this audio format", 415)
        if code in {"AUDIO_TOO_SHORT", "AUDIO_TOO_LONG", "AUDIO_SILENT", "AUDIO_CLIPPED"}:
            hints = {
                "AUDIO_TOO_SHORT": {
                    "ru": "Запишите звук не короче 3 секунд.",
                    "kk": "Дыбысты кемінде 3 секунд жазыңыз.",
                },
                "AUDIO_TOO_LONG": {
                    "ru": "Обрежьте запись до 30 секунд.",
                    "kk": "Жазбаны 30 секундқа дейін қысқартыңыз.",
                },
                "AUDIO_SILENT": {
                    "ru": "Проверьте микрофон и запишите станок ещё раз.",
                    "kk": "Микрофонды тексеріп, станокты қайта жазыңыз.",
                },
                "AUDIO_CLIPPED": {
                    "ru": "Уменьшите громкость записи и повторите.",
                    "kk": "Жазу деңгейін азайтып, қайталаңыз.",
                },
            }
            return FiboError(
                code,
                "Audio did not pass the quality gate",
                422,
                True,
                {"retake_hints": hints[code]},
            )
        if code in {"BASELINE_MISSING", "BASELINE_VERSION_MISMATCH"}:
            return FiboError(code, "Audio baseline is missing, corrupt, or incompatible", 409, True)
        return FiboError("INTERNAL", "Audio processing failed", 500)

    async def route(self, req: AudioRouteRequest) -> AudioRouteResponse:
        clip = None
        degraded: list[str] = []
        if req.file_path:
            try:
                file_path = self._shared_path(req.file_path)
                clip = await asyncio.to_thread(load_audio, file_path, 16000)
                degraded.append("silero_vad_unavailable_energy_vad_fallback")
            except Exception as exc:
                raise self._map_audio_error(exc) from exc
        if req.mode is None and clip is None:
            raise FiboError("VALIDATION_ERROR", "Provide file_path or a voice/machine mode override", 400)
        return route_recording(req, self.settings, clip, degraded)

    async def create_baseline(self, req: BaselineCreateRequest) -> BaselineArtifact:
        if len(req.file_paths) < 3:
            raise FiboError("VALIDATION_ERROR", "Provide at least 3 normal reference clips", 400)
        file_paths = [self._shared_path(path) for path in req.file_paths]
        audio_config_path = Path("configs/audio_thresholds.yaml")
        audio_config: dict[str, Any] = {}
        if audio_config_path.exists():
            import yaml

            audio_config = yaml.safe_load(audio_config_path.read_text(encoding="utf-8")) or {}
        embedder_id = req.embedder_id or audio_config.get("embedder_id", "mfcc_baseline")
        embedder, degraded = self._embedder(str(embedder_id))
        try:
            artifact = await asyncio.to_thread(
                create_baseline,
                req.machine_id,
                file_paths,
                embedder,
                Path(self.settings.fibo_data_dir),
                f"baseline-{uuid.uuid4().hex[:8]}",
                self.settings.model_version,
                self.settings.config_version,
            )
            artifact.degraded = degraded
            metadata_path = Path(self.settings.fibo_data_dir) / Path(artifact.blob_path).with_suffix(".json")
            metadata_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
            return artifact
        except Exception as exc:
            raise self._map_audio_error(exc) from exc

    async def analyze(
        self,
        machine_id: str,
        file_path: str | None = None,
        baseline_ref: BaselineArtifact | None = None,
    ) -> AudioAnalysis:
        if file_path is None:
            raise FiboError("VALIDATION_ERROR", "Provide file_path", 400)
        if baseline_ref is None:
            metadata_path = (
                Path(self.settings.fibo_data_dir) / "baselines" / "audio" / f"{quote(machine_id, safe='')}.json"
            )
            if not metadata_path.exists():
                raise FiboError("BASELINE_MISSING", "No baseline is registered for this machine", 404)
            baseline_ref = BaselineArtifact.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        embedder, degraded = self._embedder(baseline_ref.embedder_id)
        current_path = self._shared_path(file_path)
        try:
            result = await asyncio.to_thread(
                analyze_machine_audio,
                machine_id,
                current_path,
                baseline_ref,
                embedder,
                self.settings,
            )
            result.degraded = degraded
            return result
        except Exception as exc:
            raise self._map_audio_error(exc) from exc


class MetaService:
    def __init__(self, settings: Settings, ai: "FiboAI | None" = None) -> None:
        self.settings = settings
        self.ai = ai

    def get_health(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            timestamp=datetime.now(UTC).isoformat(),
        )

    def get_ready(self) -> ReadyResponse:
        stub_mode = self.settings.ai_stub_mode
        risk_loaded = bool(
            self.ai
            and (
                self.ai.risk.predictor.artifact is not None
                or (stub_mode and self.ai.risk.predictor.adapter is not None)
            )
        )
        audio_loaded = bool(self.ai is not None)
        asr_provider = self.ai.speech.asr if self.ai else None
        asr_loaded = stub_mode or bool(asr_provider is not None and getattr(asr_provider, "_model", None) is not None)
        rag_ready = bool(self.ai is not None)
        storage_ready = False
        if self.ai is not None:
            try:
                self.ai.rag.root.mkdir(parents=True, exist_ok=True)
                storage_ready = self.ai.rag.root.is_dir() and os.access(self.ai.rag.root, os.R_OK | os.W_OK)
            except OSError:
                storage_ready = False
        # Stub mode is intentionally ready through deterministic local fallbacks.
        models = {
            "risk_model": risk_loaded,
            "audio_embedder": audio_loaded,
            "asr_whisper": asr_loaded,
            "rag_store_and_fallback": rag_ready,
        }
        ready = storage_ready and (all(models.values()) or stub_mode)
        return ReadyResponse(
            ready=ready,
            models_loaded=models,
            storage_ready=storage_ready,
        )

    def get_models_meta(self) -> ModelsMetaResponse:
        req_id = f"meta-{uuid.uuid4().hex[:8]}"
        metrics_file = Path("reports/metrics.json")
        metrics: dict[str, Any] = {}
        if metrics_file.exists():
            try:
                import json

                with open(metrics_file, encoding="utf-8") as f:
                    metrics = json.load(f)
            except Exception:
                pass

        risk_metrics = metrics.get("risk", {})
        return ModelsMetaResponse(
            request_id=req_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            models=[
                ModelMetaInfo(
                    name="risk_failure_model",
                    version="0.1.0-phase1",
                    description="AI4I 2020 trained HistGradientBoosting failure predictor with Isotonic calibration",
                    metrics=risk_metrics.get("test", {"status": "trained"}),
                ),
                ModelMetaInfo(
                    name="audio_anomaly_scorer",
                    version="0.1.0-stub",
                    description="PANNs CNN14 embedder with baseline spread floor",
                    metrics={"status": "STUB_PHASE_0"},
                ),
            ],
            system_metrics=metrics,
        )


class FiboAI:
    """Unified in-process facade for Fibo AI/ML capabilities."""

    def __init__(
        self,
        settings: Settings | None = None,
        repo: DataRepository | None = None,
        *,
        llm_client: LLMClient | None = None,
        asr_provider: ASRProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm: LLMClient = llm_client or (
            FakeLLM() if self.settings.llm_provider == "fake" else OpenAICompatClient(self.settings)
        )
        self.repository = repo or (FakeRepository() if self.settings.ai_stub_mode else None)
        self.risk = RiskService(self.settings)
        self.audio = AudioService(self.settings)
        selected_asr = asr_provider
        if selected_asr is None and self.settings.ai_stub_mode:
            selected_asr = FakeASR()
        self.speech = SpeechService(self.settings, self.llm, selected_asr)
        self.vision = VisionService(self.settings, self.llm, self.repository)
        self.rag = RAGService(self.settings, self.llm)
        self.incident = IncidentService(
            self.settings,
            self.risk,
            self.rag,
            self.speech,
            self.audio,
            self.llm,
            vision_svc=self.vision,
        )
        self.assistant = AssistantService(self.settings, self.repository, self.llm, self.rag)
        self.meta = MetaService(self.settings, self)

    @classmethod
    def from_env(cls) -> "FiboAI":
        return cls(get_settings())
