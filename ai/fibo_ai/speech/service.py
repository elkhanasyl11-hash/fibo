"""Speech facade service with local ASR and deterministic parsing fallback."""

import asyncio
import uuid
from pathlib import Path

from fibo_ai.audio.io import load_audio, resolve_audio_path
from fibo_ai.core.errors import ASRLowConfidenceError, FiboError, ModelNotReadyError
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.safety.rules import SafetyEngine, get_safety_engine
from fibo_ai.schemas.common import Confidence, Usage
from fibo_ai.schemas.speech import (
    ParsedSymptom,
    ParseRequest,
    TranscribeRequest,
    TranscribeResponse,
)
from fibo_ai.settings import Settings
from fibo_ai.speech.asr import (
    ASRProvider,
    FasterWhisperASR,
    hallucination_reason,
)
from fibo_ai.speech.parse import parse_symptom


class SpeechService:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient | None = None,
        asr: ASRProvider | None = None,
        safety_engine: SafetyEngine | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.asr = asr
        self.safety_engine = safety_engine or get_safety_engine()
        self._semaphore = asyncio.Semaphore(1)

    def _asr(self) -> ASRProvider:
        if self.asr is not None:
            return self.asr
        if self.settings.asr_provider != "faster_whisper":
            raise ModelNotReadyError(f"Unknown ASR provider: {self.settings.asr_provider}")
        self.asr = FasterWhisperASR(self.settings)
        return self.asr

    async def transcribe(self, req: TranscribeRequest) -> TranscribeResponse:
        if not req.file_path:
            raise FiboError("VALIDATION_ERROR", "Provide file_path for transcription", 400)
        try:
            path = resolve_audio_path(req.file_path, Path(self.settings.fibo_shared_dir))
            if not path.is_file():
                raise FileNotFoundError(path)
            clip = await asyncio.to_thread(load_audio, path, 16000)
        except FileNotFoundError as exc:
            raise FiboError("FILE_NOT_FOUND", "Audio file was not found", 404) from exc
        except ValueError as exc:
            raise FiboError("UNSUPPORTED_MEDIA", "Could not decode this audio format", 415) from exc
        except RuntimeError as exc:
            raise FiboError("MODEL_NOT_READY", str(exc), 503, True) from exc

        terms = [
            *req.catalog_machines,
            *{
                "metalworking": ["ЧПУ", "токарный", "фрезерный", "шпиндель"],
                "bakery": ["печь", "тестомес", "конвейер"],
                "confectionery": ["темпер", "миксер", "формовщик"],
                "sewing": ["игла", "челнок", "лапка"],
                "dairy": ["пастеризатор", "охладитель", "насос"],
            }[req.profile.value],
            "ЧПУ-2",
            "шпиндель",
            "подшипник",
            "смазка",
            "түтін",
            "мойынтірек",
            "майлау",
            "bearing",
            "spindle",
            "lubrication",
        ]
        prompt = ", ".join(dict.fromkeys(term for term in terms if term))[:500]
        try:
            async with self._semaphore:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._asr().transcribe,
                        clip.samples,
                        clip.sample_rate,
                        req.language_hint,
                        prompt,
                    ),
                    timeout=45.0,
                )
        except ASRLowConfidenceError:
            raise
        except ModelNotReadyError:
            raise
        except TimeoutError as exc:
            raise FiboError("MODEL_NOT_READY", "ASR timed out", 503, True) from exc
        except Exception as exc:
            raise FiboError(
                "MODEL_NOT_READY",
                "ASR model could not transcribe this recording",
                503,
                True,
                {"reason": type(exc).__name__},
            ) from exc
        reason = hallucination_reason(result)
        if reason:
            raise ASRLowConfidenceError(
                "Transcript failed the hallucination/quality guard",
                details={
                    "reason": reason,
                    "retake_hints": {
                        "ru": "Запишите сообщение ещё раз в тихом месте.",
                        "kk": "Хабарламаны тыныш жерде қайта жазыңыз.",
                    },
                },
            )
        average_logprob = (
            sum(segment.avg_logprob for segment in result.segments) / len(result.segments) if result.segments else -1.0
        )
        confidence = (
            Confidence.high
            if average_logprob >= -0.35
            else Confidence.medium
            if average_logprob >= -0.7
            else Confidence.low
        )
        return TranscribeResponse(
            request_id=f"asr-{uuid.uuid4().hex[:8]}",
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            text=result.text,
            language=result.language,
            segments=result.segments,
            confidence=confidence,
            duration_s=result.duration_s,
            usage=Usage(asr_seconds=result.duration_s),
        )

    async def parse(
        self,
        req: ParseRequest,
        preferred_machine: str | None = None,
    ) -> ParsedSymptom:
        llm = self.llm if self.settings.llm_provider != "fake" else None
        parsed, degraded, input_tokens, output_tokens = await parse_symptom(
            text=req.text,
            profile=req.profile,
            catalog_machines=req.catalog_machines,
            safety_engine=self.safety_engine,
            llm=llm,
            preferred_machine=preferred_machine,
            request_id=f"parse-{uuid.uuid4().hex[:8]}",
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
        )
        parsed.degraded = degraded
        parsed.usage = Usage(
            llm_input_tokens=input_tokens,
            llm_output_tokens=output_tokens,
        )
        return parsed
