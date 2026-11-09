"""Per-machine baseline creation, integrity checks, and scoring."""

import hashlib
import io
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
import yaml
from numpy.typing import NDArray
from scipy.signal import spectrogram, welch

from fibo_ai.audio.embedder import AudioEmbedder, make_windows
from fibo_ai.audio.io import load_audio
from fibo_ai.schemas.audio import BaselineArtifact


def _config() -> dict[str, Any]:
    with Path("configs/audio_thresholds.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def _spectrum(waveform: NDArray[Any], sample_rate: int) -> tuple[NDArray[Any], NDArray[Any]]:
    nperseg = min(4096, max(256, waveform.size))
    frequencies, power = welch(waveform, fs=sample_rate, nperseg=nperseg)
    return frequencies.astype(np.float32), power.astype(np.float32)


def create_baseline(
    machine_id: str,
    file_paths: list[Path],
    embedder: AudioEmbedder,
    data_dir: Path,
    request_id: str,
    model_version: str,
    config_version: str,
) -> BaselineArtifact:
    if len(file_paths) < 3:
        raise ValueError("BASELINE_REQUIRES_THREE_CLIPS")
    config = _config()
    window = config.get("window", {})
    duration_s = float(window.get("duration_s", 2.0))
    overlap = float(window.get("overlap", 0.5))
    embeddings: list[NDArray[Any]] = []
    spectra: list[NDArray[Any]] = []
    spectrograms: list[NDArray[Any]] = []
    spectrum_freqs: NDArray[Any] | None = None
    sample_rate_16k = 16000
    for path in file_paths:
        model_clip = load_audio(path, embedder.sample_rate)
        windows = make_windows(model_clip.samples, embedder.sample_rate, duration_s, overlap)
        embeddings.extend(embedder.embed(part) for part in windows)
        descriptor_clip = load_audio(path, sample_rate_16k)
        frequencies, power = _spectrum(descriptor_clip.samples, sample_rate_16k)
        if spectrum_freqs is None:
            spectrum_freqs = frequencies
        elif not np.array_equal(spectrum_freqs, frequencies):
            power = np.interp(spectrum_freqs, frequencies, power).astype(np.float32)
        spectra.append(power)
        descriptor_windows = make_windows(descriptor_clip.samples, sample_rate_16k, duration_s, overlap)
        for descriptor_window in descriptor_windows:
            _, _, spec = spectrogram(descriptor_window, fs=sample_rate_16k, nperseg=512, noverlap=384, nfft=512)
            spectrograms.append(10.0 * np.log10(np.maximum(spec, 1e-12)).astype(np.float32))

    matrix = np.asarray(embeddings, dtype=np.float32)
    centroid = matrix.mean(axis=0)
    centroid_norm = float(np.linalg.norm(centroid))
    if centroid_norm > 1e-12:
        centroid /= centroid_norm
    distances = np.clip(1.0 - matrix @ centroid, 0.0, 2.0)
    aggregate = str(window.get("aggregate", "p90"))
    if aggregate == "p90":
        clip_distances: list[float] = []
        offset = 0
        for path in file_paths:
            clip = load_audio(path, embedder.sample_rate)
            windows_count = len(make_windows(clip.samples, embedder.sample_rate, duration_s, overlap))
            clip_distances.append(float(np.quantile(distances[offset : offset + windows_count], 0.90)))
            offset += windows_count
        baseline_distances = np.asarray(clip_distances, dtype=np.float32)
    else:
        baseline_distances = distances
    mean_distance = float(np.mean(baseline_distances))
    spread = float(np.std(baseline_distances, ddof=1)) if baseline_distances.size > 1 else 0.0
    spread_floor = float(config.get("global_priors", {}).get("spread_floor", 0.05))
    spectrum_mean = np.mean(np.vstack(spectra), axis=0)
    if spectrum_freqs is None:
        raise ValueError("BASELINE_EMPTY")

    safe_id = quote(machine_id, safe="")
    blob_path = Path("baselines/audio") / f"{safe_id}.npz"
    absolute_path = data_dir / blob_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        centroid=centroid,
        ref_embeddings=matrix,
        mean_distance=np.array(mean_distance, dtype=np.float32),
        spread=np.array(spread, dtype=np.float32),
        spread_floor=np.array(spread_floor, dtype=np.float32),
        spectrum_mean=spectrum_mean,
        spectrum_freqs=spectrum_freqs,
        spectrogram_mean=np.mean(np.stack(spectrograms), axis=0),
    )
    payload = buffer.getvalue()
    absolute_path.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    from datetime import UTC, datetime

    return BaselineArtifact(
        request_id=request_id,
        model_version=model_version,
        config_version=config_version,
        machine_id=machine_id,
        embedder_id=embedder.embedder_id,
        embedder_version=embedder.version,
        blob_path=blob_path.as_posix(),
        sha256=sha,
        created_at=datetime.now(UTC).isoformat(),
        stats={
            "mean_dist": mean_distance,
            "spread": spread,
            "spread_floor": spread_floor,
            "reference_windows": float(len(embeddings)),
        },
        window_params={
            "duration_s": duration_s,
            "overlap": overlap,
            "aggregate_p90": float(aggregate == "p90"),
        },
    )


def load_baseline(reference: BaselineArtifact, data_dir: Path, embedder: AudioEmbedder) -> dict[str, NDArray[Any]]:
    if reference.embedder_id != embedder.embedder_id or reference.embedder_version != embedder.version:
        raise ValueError("BASELINE_VERSION_MISMATCH")
    relative = Path(reference.blob_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("BASELINE_VERSION_MISMATCH")
    path = (data_dir / relative).resolve()
    if data_dir.resolve() not in path.parents or not path.is_file():
        raise ValueError("BASELINE_MISSING")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != reference.sha256:
        raise ValueError("BASELINE_VERSION_MISMATCH")
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def score_clip(
    waveform: NDArray[Any],
    embedder: AudioEmbedder,
    baseline: dict[str, NDArray[Any]],
    duration_s: float,
    overlap: float,
    aggregate: str = "p90",
) -> tuple[float, NDArray[Any], NDArray[Any]]:
    window_embeddings = np.asarray(
        [embedder.embed(part) for part in make_windows(waveform, embedder.sample_rate, duration_s, overlap)],
        dtype=np.float32,
    )
    distances = np.clip(1.0 - window_embeddings @ baseline["centroid"], 0.0, 2.0)
    score = float(np.quantile(distances, 0.90) if aggregate == "p90" else np.mean(distances))
    spread = max(float(baseline["spread"].item()), float(baseline["spread_floor"].item()))
    z_score = (score - float(baseline["mean_distance"].item())) / spread
    return z_score, window_embeddings, distances
