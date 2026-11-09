"""Baseline-relative machine sound scoring and structured response assembly."""

import uuid
from pathlib import Path
from typing import Any

import yaml

from fibo_ai.audio.baseline import load_baseline, score_clip
from fibo_ai.audio.descriptors import extract_descriptors, render_descriptors
from fibo_ai.audio.embedder import AudioEmbedder
from fibo_ai.audio.io import load_audio
from fibo_ai.audio.spectrogram import render_spectrogram_pair
from fibo_ai.schemas.audio import AudioAnalysis, BaselineArtifact
from fibo_ai.schemas.common import Confidence, IncidentLevel, Usage
from fibo_ai.settings import Settings


def analyze_machine_audio(
    machine_id: str,
    file_path: Path,
    baseline_ref: BaselineArtifact,
    embedder: AudioEmbedder,
    settings: Settings,
) -> AudioAnalysis:
    if baseline_ref.machine_id != machine_id:
        raise ValueError("BASELINE_VERSION_MISMATCH")
    data_dir = Path(settings.fibo_data_dir)
    baseline = load_baseline(baseline_ref, data_dir, embedder)
    model_clip = load_audio(file_path, embedder.sample_rate)
    window_params = baseline_ref.window_params
    z_score, window_embeddings, _ = score_clip(
        model_clip.samples,
        embedder,
        baseline,
        duration_s=float(window_params.get("duration_s", 2.0)),
        overlap=float(window_params.get("overlap", 0.5)),
        aggregate="p90" if float(window_params.get("aggregate_p90", 1.0)) else "mean",
    )
    descriptor_clip = load_audio(file_path, 16000)
    descriptors = extract_descriptors(descriptor_clip.samples, 16000, baseline)
    descriptors_ru, descriptors_kk = render_descriptors(descriptors, z_score)
    config_path = Path("configs/audio_thresholds.yaml")
    with config_path.open(encoding="utf-8") as stream:
        config: dict[str, Any] = yaml.safe_load(stream) or {}
    thresholds = config.get("thresholds", {})
    normal_max = float(thresholds.get("normal_max_z", 2.0))
    critical_min = float(thresholds.get("attention_max_z", 3.0))
    if z_score < normal_max:
        level = IncidentLevel.normal
    elif z_score < critical_min:
        level = IncidentLevel.attention
    else:
        level = IncidentLevel.critical
    spectrogram_b64 = render_spectrogram_pair(descriptor_clip.samples, 16000, baseline)
    return AudioAnalysis(
        request_id=f"audio-{uuid.uuid4().hex[:8]}",
        model_version=settings.model_version,
        config_version=settings.config_version,
        machine_id=machine_id,
        route="machine",
        level=level,
        z_score=round(z_score, 4),
        confidence=Confidence.high,
        descriptors=descriptors,
        descriptors_text_ru=descriptors_ru,
        descriptors_text_kk=descriptors_kk,
        spectrogram_png_b64=spectrogram_b64,
        quality={
            "duration_s": round(descriptor_clip.duration_s, 3),
            "rms": round(descriptor_clip.rms, 6),
            "clipping_ratio": round(descriptor_clip.clipping_ratio, 6),
            "embedder_sample_rate": embedder.sample_rate,
            "window_count": len(window_embeddings),
        },
        baseline_ref=baseline_ref,
        usage=Usage(embed_calls=len(window_embeddings)),
    )
