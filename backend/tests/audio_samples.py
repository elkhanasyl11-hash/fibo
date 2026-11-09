"""Tiny synthetic recordings for tests (no real audio files in the repository)."""

import io

import numpy as np
import soundfile as sf


def tone(seconds: float = 2.0, rate: int = 16000, freq: float = 220.0, channels: int = 1) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    wave = 0.3 * np.sin(2 * np.pi * freq * t)
    return np.stack([wave] * channels, axis=1) if channels > 1 else wave


def wav_bytes(data: np.ndarray, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, data, rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def ogg_opus_bytes(data: np.ndarray, rate: int = 48000) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, data, rate, format="OGG", subtype="OPUS")
    return buffer.getvalue()


def silence_wav(seconds: float = 2.0) -> bytes:
    return wav_bytes(np.zeros(int(seconds * 16000)))


def machine_sound(seed: int, seconds: float = 10.0, anomaly: str | None = None) -> np.ndarray:
    """Synthetic healthy machine: 120 Hz hum + harmonic + light noise. Anomalies: noise, tone, knock."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * 16000)) / 16000
    wave = (
        0.2 * np.sin(2 * np.pi * 120 * t) + 0.1 * np.sin(2 * np.pi * 240 * t) + 0.03 * rng.normal(size=t.size)
    )
    if anomaly == "noise":
        wave += 0.05 * rng.normal(size=t.size)
    elif anomaly == "tone":
        wave += 0.15 * np.sin(2 * np.pi * 3000 * t)
    elif anomaly == "knock":
        wave[:: 16000 // 4] += 0.9  # four sharp impacts per second
    return wave
