"""Lightweight speech-vs-machine routing with an offline VAD fallback."""

import uuid
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fibo_ai.audio.io import AudioClip
from fibo_ai.schemas.audio import AudioRouteRequest, AudioRouteResponse
from fibo_ai.schemas.common import Confidence
from fibo_ai.settings import Settings


def estimate_speech_ratio(clip: AudioClip) -> float:
    frame_size = max(1, int(0.03 * clip.sample_rate))
    rms_values: list[float] = []
    zcr_values: list[float] = []
    centroid_values: list[float] = []
    for start in range(0, clip.samples.size - frame_size + 1, frame_size):
        frame = clip.samples[start : start + frame_size]
        rms_values.append(float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))))
        zcr_values.append(float(np.mean(np.diff(np.signbit(frame)))))
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(frame.size)))
        freqs = np.fft.rfftfreq(frame.size, 1 / clip.sample_rate)
        centroid_values.append(float(np.sum(freqs * spectrum) / max(float(np.sum(spectrum)), 1e-12)))
    rms = np.asarray(rms_values)
    zcr = np.asarray(zcr_values)
    centroid = np.asarray(centroid_values)
    if rms.size == 0:
        return 0.0
    active = rms >= max(0.006, float(np.quantile(rms, 0.55)) * 0.45)
    voice_like = active & (zcr >= 0.015) & (zcr <= 0.35) & (centroid >= 180.0) & (centroid <= 5000.0)
    return float(np.mean(voice_like))


def route_recording(
    req: AudioRouteRequest,
    settings: Settings,
    clip: AudioClip | None,
    degraded: list[str] | None = None,
) -> AudioRouteResponse:
    if req.mode not in (None, "voice", "machine"):
        raise ValueError("INVALID_AUDIO_ROUTE")
    config_path = Path("configs/audio_thresholds.yaml")
    with config_path.open(encoding="utf-8") as stream:
        config: dict[str, Any] = yaml.safe_load(stream) or {}
    threshold = float(config.get("quality", {}).get("speech_ratio_voice", 0.5))
    ratio = estimate_speech_ratio(clip) if clip is not None else (1.0 if req.mode == "voice" else 0.0)
    route = req.mode or ("voice" if ratio >= threshold else "machine")
    mixed = route == "voice" and threshold * 0.6 <= ratio < threshold
    return AudioRouteResponse(
        request_id=f"route-{uuid.uuid4().hex[:8]}",
        model_version=settings.model_version,
        config_version=settings.config_version,
        route=route,
        speech_ratio=round(ratio, 4),
        confidence=Confidence.high
        if req.mode
        else (Confidence.high if abs(ratio - threshold) >= 0.1 else Confidence.low),
        also_analyze_background=bool(mixed and req.also_analyze_background),
        degraded=degraded or [],
    )
