"""Audio decoding and quality gates, shared by baseline and scoring paths."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from numpy.typing import NDArray


@dataclass(frozen=True)
class AudioClip:
    samples: NDArray[Any]
    sample_rate: int
    duration_s: float
    rms: float
    clipping_ratio: float


def _audio_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path("configs/audio_thresholds.yaml")
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def resolve_audio_path(file_path: str, shared_dir: Path) -> Path:
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = shared_dir / candidate
    resolved = candidate.resolve()
    root = shared_dir.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Audio path must be inside FIBO_SHARED_DIR")
    if not resolved.is_file():
        raise FileNotFoundError(f"Audio file does not exist: {resolved.name}")
    return resolved


def load_audio(file_path: Path, sample_rate: int) -> AudioClip:
    """Decode with ffmpeg to mono float32 at the requested model's native rate."""
    config = _audio_config()
    quality = config.get("quality", {})
    max_bytes = int(quality.get("max_file_bytes", 15 * 1024 * 1024))
    if file_path.stat().st_size > max_bytes:
        raise ValueError("FILE_TOO_LARGE")
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(file_path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=45)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required to decode audio") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("UNSUPPORTED_MEDIA") from exc
    samples = np.frombuffer(result.stdout, dtype="<f4").copy()
    if samples.size == 0:
        raise ValueError("AUDIO_SILENT")
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    duration = float(samples.size / sample_rate)
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    clipping = float(np.mean(np.abs(samples) >= 0.999))
    minimum = float(quality.get("min_duration_s", 3.0))
    maximum = float(quality.get("max_duration_s", 30.0))
    min_rms = float(quality.get("min_rms", 0.005))
    max_clipping = float(quality.get("max_clipping_ratio", 0.05))
    if duration < minimum:
        raise ValueError("AUDIO_TOO_SHORT")
    if duration > maximum:
        raise ValueError("AUDIO_TOO_LONG")
    if rms < min_rms:
        raise ValueError("AUDIO_SILENT")
    if clipping > max_clipping:
        raise ValueError("AUDIO_CLIPPED")
    return AudioClip(samples, sample_rate, duration, rms, clipping)
