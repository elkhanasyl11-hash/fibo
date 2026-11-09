"""Voice-to-card orchestrator with partial-stage degradation and deterministic fallback."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import yaml

from fibo_ai.core.errors import FiboError
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.incident.card import draft_to_card, template_card
from fibo_ai.rag.answer import verify_card_citations
from fibo_ai.rag.service import RAGService
from fibo_ai.safety.guard import enforce_safety_guard
from fibo_ai.safety.rules import SafetyEngine, get_safety_engine
from fibo_ai.schemas.common import Confidence, IncidentLevel, Lang, Usage
from fibo_ai.schemas.incident import (
    IncidentAnalyzeRequest,
    IncidentAnalyzeResponse,
    IncidentCardDraft,
    IncidentSignals,
)
from fibo_ai.schemas.rag import ManualQueryRequest
from fibo_ai.schemas.risk import ExternalSignals, MachineReadings, RiskRequest, RiskResult
from fibo_ai.schemas.speech import ParseRequest, TranscribeRequest
from fibo_ai.schemas.vision import CompareRequest, PanelRequest
from fibo_ai.settings import Settings
from fibo_ai.speech.service import SpeechService
from fibo_ai.vision.service import VisionService


class IncidentService:
    def __init__(
        self,
        settings: Settings,
        risk_svc: Any,
        rag_svc: RAGService,
        speech_svc: SpeechService,
        audio_svc: Any,
        llm: LLMClient | None = None,
        safety_engine: SafetyEngine | None = None,
        vision_svc: VisionService | None = None,
        *,
        force_llm: bool = False,
    ) -> None:
        self.settings = settings
        self.risk_svc = risk_svc
        self.rag_svc = rag_svc
        self.speech_svc = speech_svc
        self.audio_svc = audio_svc
        self.vision_svc = vision_svc
        self.llm = llm
        self.safety_engine = safety_engine or get_safety_engine()
        self.force_llm = force_llm

    async def _transcribe(self, req: IncidentAnalyzeRequest) -> tuple[str, float, int, int, list[str]]:
        if not req.voice_file_path:
            return req.text or "", 0.0, 0, 0, []
        try:
            result = await self.speech_svc.transcribe(
                TranscribeRequest(
                    file_path=req.voice_file_path,
                    language_hint=req.lang,
                    profile=req.profile,
                    catalog_machines=req.catalog_machines,
                )
            )
            return (
                result.text,
                result.usage.asr_seconds,
                result.usage.llm_input_tokens,
                result.usage.llm_output_tokens,
                result.degraded,
            )
        except Exception as exc:
            fallback = req.text or ""
            code = exc.code if isinstance(exc, FiboError) else type(exc).__name__
            return fallback, 0.0, 0, 0, [f"asr_unavailable:{code}"]

    async def _analyze_audio(self, req: IncidentAnalyzeRequest, machine_id: str | None) -> tuple[Any | None, list[str]]:
        if not req.audio_file_path:
            return None, []
        if not req.baseline_ref:
            return None, ["audio_baseline_missing"]
        target_machine = machine_id or req.baseline_ref.machine_id
        try:
            result = await self.audio_svc.analyze(target_machine, req.audio_file_path, req.baseline_ref)
            return result, result.degraded
        except Exception as exc:
            code = exc.code if isinstance(exc, FiboError) else type(exc).__name__
            return None, [f"audio_analysis_failed:{code}"]

    async def _analyze_vision(self, req: IncidentAnalyzeRequest) -> tuple[Any | None, Any | None, list[str]]:
        panel_task = (
            self.vision_svc.read_panel(
                PanelRequest(
                    file_path=req.panel_photo_path,
                    machine_id=req.machine_id,
                    workshop_id=req.workshop_id,
                    lang=req.lang,
                )
            )
            if self.vision_svc and req.panel_photo_path
            else asyncio.sleep(0, result=None)
        )
        tool_task = (
            self.vision_svc.compare_tool(
                CompareRequest(
                    file_path_reference=req.tool_reference_photo_path,
                    file_path_current=req.tool_photo_path,
                    lang=req.lang,
                )
            )
            if self.vision_svc and req.tool_photo_path and req.tool_reference_photo_path
            else asyncio.sleep(0, result=None)
        )
        panel_result, tool_result = await asyncio.gather(panel_task, tool_task, return_exceptions=True)
        degraded: list[str] = []
        panel = panel_result if not isinstance(panel_result, BaseException) else None
        tool = tool_result if not isinstance(tool_result, BaseException) else None
        for label, item in (("panel", panel_result), ("tool_compare", tool_result)):
            if isinstance(item, BaseException):
                code = item.code if isinstance(item, FiboError) else type(item).__name__
                degraded.append(f"{label}_unavailable:{code}")
            elif item is not None:
                degraded.extend(item.degraded)
        if req.tool_photo_path and not req.tool_reference_photo_path:
            degraded.append("tool_reference_photo_missing")
        return panel, tool, degraded

    @staticmethod
    def _level(
        risk: RiskResult,
        safety_force_stop: bool,
        audio: Any | None,
        urgency: str,
        tool: Any | None = None,
    ) -> IncidentLevel:
        config_path = Path("configs/levels.yaml")
        config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        thresholds = config.get("thresholds", {})
        risk_thresholds = thresholds.get("risk_index", {})
        audio_thresholds = thresholds.get("audio_z", {})
        if safety_force_stop:
            return IncidentLevel.critical
        if tool and tool.wear_level == "severe" and tool.confidence == Confidence.high:
            return IncidentLevel.critical
        if risk.risk_index >= float(risk_thresholds.get("critical", 0.70)):
            return IncidentLevel.critical
        if audio and audio.z_score >= float(audio_thresholds.get("critical", 3.0)):
            return IncidentLevel.critical
        if (
            risk.risk_index >= float(risk_thresholds.get("attention", 0.40))
            or (audio and audio.z_score >= float(audio_thresholds.get("attention", 2.0)))
            or urgency == "high"
        ):
            return IncidentLevel.attention
        return IncidentLevel.normal

    @staticmethod
    def _confidence(risk: RiskResult) -> Confidence:
        used = len(risk.coverage.used)
        if risk.ood_warning or used <= 1:
            return Confidence.low if risk.ood_warning else Confidence.medium
        return Confidence.high if used >= 3 else Confidence.medium

    def _card_prompt(
        self,
        text: str,
        machine_id: str | None,
        lang: Lang,
        level: IncidentLevel,
        findings: list[str],
        fragments: list[Any],
    ) -> str:
        prompt_path = Path("prompts") / lang.value / "card_v1_0.txt"
        base = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        manual = "\n".join(
            f'<untrusted_manual_page page="{item.page}" section="{item.section}">{item.snippet}</untrusted_manual_page>'
            for item in fragments
        )
        return (
            f"{base}\nMachine={machine_id or 'unresolved'}; deterministic_level={level.value}; "
            f"language={lang.value}.\n<untrusted_transcript>{text[:2000]}</untrusted_transcript>"
            f"\nObserved findings={findings}\nRetrieved pages={sorted({item.page for item in fragments})}"
            f"\n{manual}"
        )

    async def _draft(
        self,
        *,
        text: str,
        machine_id: str | None,
        parsed: Any,
        lang: Lang,
        level: IncidentLevel,
        findings: list[str],
        fragments: list[Any],
        degraded: list[str],
    ) -> tuple[IncidentCardDraft | None, Usage]:
        if self.llm is None or (self.settings.llm_provider == "fake" and not self.force_llm):
            return None, Usage()
        try:
            draft, usage = await self.llm.generate_json(
                self._card_prompt(text, machine_id, lang, level, findings, fragments),
                IncidentCardDraft,
                temperature=0.0,
                timeout_s=12.0,
            )
            return draft, usage
        except Exception as exc:
            degraded.append(f"card_llm_fallback:{type(exc).__name__}")
            return None, Usage()

    async def analyze(self, req: IncidentAnalyzeRequest) -> IncidentAnalyzeResponse:
        request_id = f"inc-{uuid.uuid4().hex[:8]}"
        previous = req.incident_context or {}
        answered_machine = (req.answers or {}).get("machine_id")
        preferred_machine = req.machine_id or answered_machine or previous.get("machine_id")
        transcript_task = self._transcribe(req)
        audio_task = self._analyze_audio(req, preferred_machine)
        transcript_result, audio_result, vision_result = await asyncio.gather(
            transcript_task, audio_task, self._analyze_vision(req), return_exceptions=True
        )
        degraded: list[str] = []
        asr_seconds = 0.0
        asr_input_tokens = asr_output_tokens = 0
        if isinstance(transcript_result, BaseException):
            source_text = req.text or ""
            degraded.append(f"asr_unavailable:{type(transcript_result).__name__}")
        else:
            (
                source_text,
                asr_seconds,
                asr_input_tokens,
                asr_output_tokens,
                asr_degraded,
            ) = transcript_result
            degraded.extend(asr_degraded)
        if isinstance(audio_result, BaseException):
            audio, audio_degraded = None, [f"audio_analysis_failed:{type(audio_result).__name__}"]
        else:
            audio, audio_degraded = audio_result
        degraded.extend(audio_degraded)
        if isinstance(vision_result, BaseException):
            panel, tool, vision_degraded = (
                None,
                None,
                [f"vision_unavailable:{type(vision_result).__name__}"],
            )
        else:
            panel, tool, vision_degraded = vision_result
        degraded.extend(vision_degraded)

        catalog = req.catalog_machines
        parse_response = await self.speech_svc.parse(
            ParseRequest(
                text=source_text,
                profile=req.profile,
                catalog_machines=catalog,
            ),
            preferred_machine=preferred_machine,
        )
        degraded.extend(parse_response.degraded)
        resolved_machine = preferred_machine or parse_response.machine_id
        panel_alarms = panel.alarms if panel else []
        safety = self.safety_engine.evaluate(" ".join([source_text, *panel_alarms]))
        triggers = sorted({*safety.triggers, *parse_response.safety_flags})

        if resolved_machine:
            rag_response = await self.rag_svc.query_manual(
                ManualQueryRequest(
                    machine_id=resolved_machine,
                    query=(
                        f"{parse_response.symptom_category} "
                        f"{source_text or parse_response.symptom_text} {' '.join(panel_alarms)} "
                        f"{tool.evidence if tool else ''} spindle lubrication смазка"
                    ),
                    top_k=5,
                )
            )
            fragments = rag_response.fragments
            if rag_response.general_safety_fallback:
                degraded.append("manual_not_found_general_safety_fallback")
        else:
            fragments = []
            degraded.append("machine_resolution_needs_clarification")

        machine_for_risk = resolved_machine or "machine-unresolved"
        risk_req = RiskRequest(
            machine_id=machine_for_risk,
            profile=req.profile,
            readings=panel.readings if panel else MachineReadings(),
            context=req.context,
            signals=ExternalSignals(
                audio_z=audio.z_score if audio else None,
                voice_urgency=parse_response.urgency.value,
                photo_wear=tool.wear_level if tool else None,
                photo_wear_confidence=tool.confidence.value if tool else "medium",
            ),
        )
        risk = await self.risk_svc.predict(risk_req)
        level = self._level(risk, safety.force_stop, audio, parse_response.urgency.value, tool)
        confidence = self._confidence(risk)
        findings = [parse_response.symptom_text] if source_text.strip() else []
        if panel:
            visible_readings = [
                f"{name}={value:g}" for name, value in panel.readings.model_dump().items() if value is not None
            ]
            findings.extend(visible_readings)
            findings.extend(panel_alarms)
        if tool:
            findings.append(f"Tool wear: {tool.wear_level} ({tool.confidence.value} confidence)")
        if audio is not None:
            findings.append(f"Audio deviation: {audio.z_score:+.2f}σ")
        if not findings:
            findings.append(
                "Не удалось распознать сообщение; отправьте голосовое ещё раз."
                if req.lang == Lang.ru
                else "Хабарлама танылмады; дауыстық жазбаны қайта жіберіңіз."
                if req.lang == Lang.kk
                else "The message could not be transcribed; please resend it."
            )

        draft, llm_usage = await self._draft(
            text=source_text,
            machine_id=resolved_machine,
            parsed=parse_response,
            lang=req.lang,
            level=level,
            findings=findings,
            fragments=fragments,
            degraded=degraded,
        )
        if draft is None:
            card = template_card(
                machine_id=resolved_machine,
                parsed=parse_response,
                lang=req.lang,
                level=level,
                confidence=confidence,
                findings=findings,
                fragments=fragments,
            )
        else:
            card = draft_to_card(
                draft,
                machine_id=resolved_machine,
                lang=req.lang,
                level=level,
                confidence=confidence,
                fallback_findings=findings,
            )
        card.clarifying_question = (
            parse_response.clarifying_prompt
            if parse_response.needs_clarification
            else (card.clarifying_question or None)
        )
        card, _verified_pages = verify_card_citations(card, [fragment.page for fragment in fragments])
        card = enforce_safety_guard(card, safety.model_copy(update={"triggers": triggers}))
        card.card_text = card.card_text[:4096]
        signals = IncidentSignals(
            machine_id=resolved_machine,
            extracted_readings=panel.readings if panel else MachineReadings(),
            audio_z=audio.z_score if audio else None,
            audio_level=audio.level if audio else None,
            photo_wear=tool.wear_level if tool else None,
            symptom_category=parse_response.symptom_category,
            safety_triggers=triggers,
        )
        usage = Usage(
            asr_seconds=asr_seconds,
            llm_output_tokens=(
                asr_output_tokens
                + llm_usage.llm_output_tokens
                + parse_response.usage.llm_output_tokens
                + (panel.usage.llm_output_tokens if panel else 0)
                + (tool.usage.llm_output_tokens if tool else 0)
            ),
            llm_input_tokens=(
                asr_input_tokens
                + llm_usage.llm_input_tokens
                + parse_response.usage.llm_input_tokens
                + (panel.usage.llm_input_tokens if panel else 0)
                + (tool.usage.llm_input_tokens if tool else 0)
            ),
            embed_calls=len(fragments),
            vision_calls=(panel.usage.vision_calls if panel else 0) + (tool.usage.vision_calls if tool else 0),
            est_cost_usd=(panel.usage.est_cost_usd if panel else 0.0) + (tool.usage.est_cost_usd if tool else 0.0),
        )
        return IncidentAnalyzeResponse(
            request_id=request_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            card=card,
            signals=signals,
            risk=risk,
            degraded=list(dict.fromkeys(degraded)),
            usage=usage,
        )
