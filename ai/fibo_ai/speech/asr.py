"""Local Faster-Whisper ASR, deterministic test provider, and hallucination checks."""

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import yaml
from numpy.typing import NDArray

from fibo_ai.core.errors import ASRLowConfidenceError, ModelNotReadyError
from fibo_ai.schemas.common import Lang
from fibo_ai.schemas.speech import TranscriptSegment
from fibo_ai.settings import Settings

ALLOWED_LANGUAGES = {Lang.ru, Lang.kk, Lang.en}
DOMAIN_TERMS = [
    "ЧПУ",
    "шпиндель",
    "подшипник",
    "смазка",
    "станок",
    "түтін",
    "мойынтірек",
    "майлау",
    "spindle",
    "bearing",
    "lubrication",
]


@dataclass(frozen=True)
class ASRResult:
    text: str
    language: Lang
    segments: list[TranscriptSegment]
    duration_s: float


class ASRProvider(Protocol):
    def transcribe(
        self,
        waveform: NDArray[np.float32],
        sample_rate: int,
        language_hint: Lang | None,
        initial_prompt: str,
    ) -> ASRResult: ...


class FakeASR:
    """Offline ASR fixture provider; it never claims a measured transcription score."""

    def transcribe(
        self,
        waveform: NDArray[np.float32],
        sample_rate: int,
        language_hint: Lang | None,
        initial_prompt: str,
    ) -> ASRResult:
        del initial_prompt
        language = language_hint or Lang.ru
        samples = np.asarray(waveform)
        duration = float(samples.size / sample_rate)
        text = {
            Lang.ru: "ЧПУ второй: появился дым и запах гари.",
            Lang.kk: "ЧПУ екінші: түтін шықты, күйген иіс бар.",
            Lang.en: "CNC two: smoke and a burning smell appeared.",
        }[language]
        segment = TranscriptSegment(
            start_s=0.0,
            end_s=duration,
            text=text,
            no_speech_prob=0.01,
            avg_logprob=-0.2,
            compression_ratio=1.1,
        )
        return ASRResult(text, language, [segment], duration)


class FasterWhisperASR:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any = None
        self._lock = threading.Lock()

    def _get_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ModelNotReadyError(
                    "Install the optional speech dependencies to use local Faster-Whisper"
                ) from exc
            model_dir = Path(self.settings.fibo_data_dir) / "models" / "faster-whisper"
            model_dir.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                self.settings.whisper_model,
                device="cpu",
                compute_type=self.settings.whisper_compute_type,
                download_root=str(model_dir),
            )
            return self._model

    def transcribe(
        self,
        waveform: NDArray[np.float32],
        sample_rate: int,
        language_hint: Lang | None,
        initial_prompt: str,
    ) -> ASRResult:
        model = self._get_model()
        selected_language = language_hint.value if language_hint else None
        if selected_language is None:
            try:
                _language, _probability, candidates = model.detect_language(waveform)
                allowed = [
                    (language, float(probability))
                    for language, probability in candidates
                    if language in {"ru", "kk", "en"}
                ]
                if not allowed:
                    raise ASRLowConfidenceError(
                        "Speech language is outside ru/kk/en",
                        {"allowed_languages": ["ru", "kk", "en"]},
                    )
                selected_language = max(allowed, key=lambda pair: pair[1])[0]
            except ASRLowConfidenceError:
                raise
            except Exception as exc:
                raise ASRLowConfidenceError("Could not detect an allowed speech language") from exc
        if selected_language not in {lang.value for lang in ALLOWED_LANGUAGES}:
            raise ASRLowConfidenceError("Only Russian, Kazakh, and English are supported")
        segments, info = model.transcribe(
            waveform,
            language=selected_language,
            vad_filter=True,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
        )
        parsed_segments: list[TranscriptSegment] = []
        text_parts: list[str] = []
        for segment in segments:
            text_parts.append(str(segment.text).strip())
            parsed_segments.append(
                TranscriptSegment(
                    start_s=float(segment.start),
                    end_s=float(segment.end),
                    text=str(segment.text).strip(),
                    no_speech_prob=float(segment.no_speech_prob),
                    avg_logprob=float(segment.avg_logprob),
                    compression_ratio=float(segment.compression_ratio),
                )
            )
        lang = Lang(str(getattr(info, "language", selected_language)))
        return ASRResult(
            text=" ".join(part for part in text_parts if part).strip(),
            language=lang,
            segments=parsed_segments,
            duration_s=float(waveform.size / sample_rate),
        )


def hallucination_reason(result: ASRResult, config_path: Path | None = None) -> str | None:
    path = config_path or Path("configs/asr.yaml")
    config: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    guard = config.get("guard", {})
    folded = re.sub(r"\s+", " ", result.text.casefold())
    for phrase in guard.get("blacklist", []):
        if str(phrase).casefold() in folded:
            return "blacklisted_hallucination"
    if result.language not in ALLOWED_LANGUAGES:
        return "unsupported_language"
    for segment in result.segments:
        if segment.no_speech_prob > float(guard.get("max_no_speech_prob", 0.70)):
            return "high_no_speech_probability"
        if segment.avg_logprob < float(guard.get("min_avg_logprob", -1.0)):
            return "low_average_log_probability"
        if segment.compression_ratio > float(guard.get("max_compression_ratio", 2.4)):
            return "high_compression_ratio"
    if not result.text.strip():
        return "empty_transcript"
    return None
