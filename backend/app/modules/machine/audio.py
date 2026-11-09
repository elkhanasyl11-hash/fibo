"""Fibo Machine: is this machine sound different from the machine's own healthy sound?

Design goal: every number can be explained to a mechanic. No neural network: 14 classic features.

1. Clip: 10 s at 16 kHz. Longer recordings are cut; shorter ones (>= 2 s) are repeated (looped)
   up to 10 s — repeating keeps the sound's statistics, padding with silence would not.
2. Windows: 1 s with 50% overlap -> 19 windows per clip.
3. Features per window (computed once per clip on 64 ms frames, then averaged per window):
     band_0..band_7  log-mel energy (dB) of 64 mel bands grouped into 8 frequency bands
     rms_db          loudness
     centroid_hz     "centre of mass" of the spectrum (higher = brighter / more whine)
     rolloff_hz      frequency below which 85% of the energy lies
     flatness        0 = tonal (pure hum), 1 = noise-like (hiss, rattle)
     zcr             zero-crossing rate (rough noisiness)
     crest_factor    peak / RMS of the waveform (high = knocks, impacts)
4. Baseline: all windows of all baseline recordings -> per-feature mean and std. The std is
   floored at 1e-6 and at 5% of |mean| so that a feature that hardly varies cannot make
   tiny differences look huge.
5. Score of a new recording: per-feature z = (feature - mean) / std, averaged over its windows;
   audio_z = sqrt(mean(z^2)) over the 14 features (one number: how far from normal, in sigmas).
   Small baselines: a few recordings under-estimate how much a healthy machine's sound naturally
   varies, so z is divided by a tolerance factor that depends on the number of baseline recordings
   (TOLERANCE_BY_RECORDINGS). The factors were measured on DCASE 2020 slider normal clips so that
   about 5% of healthy recordings reach z >= 2 whatever the baseline size (decisions D70).
   Levels: < 2 normal, 2-3 warning, > 3 critical (settings; checked by ml/eval_audio_mimii.py).
6. Description: the features that deviate most, e.g. "энергия в полосе 4–8 кГц +3.4σ".
CPU work: call via asyncio.to_thread.
"""

import io
from dataclasses import dataclass

import librosa
import numpy as np
from matplotlib.figure import Figure

SAMPLE_RATE = 16000
CLIP_SECONDS = 10
MIN_SECONDS = 2
WINDOW_SAMPLES = SAMPLE_RATE  # 1 s
WINDOW_HOP = SAMPLE_RATE // 2  # 50% overlap
N_FFT = 1024
FRAME_HOP = 256
N_MELS = 64
N_BANDS = 8
STD_FLOOR_ABS = 1e-6
STD_FLOOR_REL = 0.05
# baseline recordings -> divide z by this (measured: 95th percentile of healthy z / 2, see D70)
TOLERANCE_BY_RECORDINGS = {1: 4.3, 2: 2.2, 3: 1.7, 4: 1.5, 5: 1.4, 10: 1.1, 20: 1.0}


def tolerance_factor(n_recordings: int) -> float:
    """Factor for the largest table entry not above n_recordings (fewer recordings = wider tolerance)."""
    eligible = [n for n in TOLERANCE_BY_RECORDINGS if n <= max(n_recordings, 1)]
    return TOLERANCE_BY_RECORDINGS[max(eligible)]


FEATURES = [f"band_{i}" for i in range(N_BANDS)] + [
    "rms_db",
    "centroid_hz",
    "rolloff_hz",
    "flatness",
    "zcr",
    "crest_factor",
]
_MEL_EDGES = librosa.mel_frequencies(n_mels=N_MELS + 2, fmin=0.0, fmax=SAMPLE_RATE / 2)


def _hz(value: float) -> str:
    return f"{value / 1000:.1f} кГц" if value >= 1000 else f"{value:.0f} Гц"


def _band_title(index: int) -> str:
    low, high = _MEL_EDGES[index * 8 + 1], _MEL_EDGES[index * 8 + 8]
    return f"энергия в полосе {_hz(low)}–{_hz(high)}"


FEATURE_TITLES_RU = {f"band_{i}": _band_title(i) for i in range(N_BANDS)} | {
    "rms_db": "громкость",
    "centroid_hz": "спектральный центр",
    "rolloff_hz": "граница 85% энергии",
    "flatness": "шумность спектра",
    "zcr": "частота пересечений нуля",
    "crest_factor": "пик-фактор (удары)",
}


class RecordingTooShortError(ValueError):
    """Less than MIN_SECONDS of audio."""


def fit_length(signal: np.ndarray) -> np.ndarray:
    """Exactly CLIP_SECONDS: cut, or loop a shorter recording."""
    target = SAMPLE_RATE * CLIP_SECONDS
    if len(signal) < SAMPLE_RATE * MIN_SECONDS:
        raise RecordingTooShortError(f"recording shorter than {MIN_SECONDS} s")
    if len(signal) >= target:
        return signal[:target]
    return np.resize(signal, target)  # np.resize repeats the array from the start


def window_features(signal: np.ndarray) -> np.ndarray:
    """(n_windows, 14) feature matrix of a 16 kHz mono signal (already fit to length)."""
    signal = signal.astype(np.float32)
    magnitude = np.abs(librosa.stft(signal, n_fft=N_FFT, hop_length=FRAME_HOP))
    log_mel = librosa.power_to_db(
        librosa.feature.melspectrogram(S=magnitude**2, sr=SAMPLE_RATE, n_mels=N_MELS), ref=1.0
    )  # absolute dB, so recordings can be compared
    rms = librosa.feature.rms(S=magnitude, frame_length=N_FFT)[0]
    centroid = librosa.feature.spectral_centroid(S=magnitude, sr=SAMPLE_RATE)[0]
    rolloff = librosa.feature.spectral_rolloff(S=magnitude, sr=SAMPLE_RATE, roll_percent=0.85)[0]
    flatness = librosa.feature.spectral_flatness(S=magnitude)[0]
    zcr = librosa.feature.zero_crossing_rate(signal, frame_length=N_FFT, hop_length=FRAME_HOP)[0]

    rows = []
    for start in range(0, len(signal) - WINDOW_SAMPLES + 1, WINDOW_HOP):
        f0, f1 = start // FRAME_HOP, (start + WINDOW_SAMPLES) // FRAME_HOP
        chunk = signal[start : start + WINDOW_SAMPLES]
        bands = log_mel[:, f0:f1].mean(axis=1).reshape(N_BANDS, N_MELS // N_BANDS).mean(axis=1)
        crest = float(np.max(np.abs(chunk)) / (np.sqrt(np.mean(chunk**2)) + 1e-10))
        rows.append(
            [
                *bands,
                20 * np.log10(rms[f0:f1].mean() + 1e-10),
                centroid[f0:f1].mean(),
                rolloff[f0:f1].mean(),
                flatness[f0:f1].mean(),
                zcr[f0:f1].mean(),
                crest,
            ]
        )
    return np.array(rows, dtype=float)


def baseline_stats(window_matrices: list[np.ndarray]) -> dict:
    """Per-feature mean/std over all windows of all baseline recordings (JSON-ready)."""
    windows = np.vstack(window_matrices)
    mean = windows.mean(axis=0)
    std = np.maximum.reduce(
        [windows.std(axis=0), np.full_like(mean, STD_FLOOR_ABS), STD_FLOOR_REL * np.abs(mean)]
    )
    return {
        "features": FEATURES,
        "mean": mean.round(6).tolist(),
        "std": std.round(6).tolist(),
        "n_windows": int(len(windows)),
        "n_recordings": len(window_matrices),
    }


@dataclass
class AudioScore:
    audio_z: float
    level: str
    z_by_feature: dict[str, float]
    description: str


def level_for(audio_z: float, warning_at: float, critical_at: float) -> str:
    if audio_z > critical_at:
        return "critical"
    return "warning" if audio_z >= warning_at else "normal"


def describe(z_by_feature: dict[str, float], top: int = 3) -> str:
    strongest = sorted(z_by_feature.items(), key=lambda item: abs(item[1]), reverse=True)[:top]
    parts = [f"{FEATURE_TITLES_RU[name]} {z:+.1f}σ" for name, z in strongest if abs(z) >= 1.0]
    return ", ".join(parts) if parts else "звук близок к эталону"


def score(windows: np.ndarray, stats: dict, warning_at: float = 2.0, critical_at: float = 3.0) -> AudioScore:
    z = ((windows - np.array(stats["mean"])) / np.array(stats["std"])).mean(axis=0)
    z = z / tolerance_factor(stats.get("n_recordings", 1))
    audio_z = float(np.sqrt(np.mean(z**2)))
    z_by_feature = {name: round(float(value), 2) for name, value in zip(FEATURES, z, strict=True)}
    return AudioScore(
        round(audio_z, 3), level_for(audio_z, warning_at, critical_at), z_by_feature, describe(z_by_feature)
    )


def spectrogram_png(baseline: np.ndarray, current: np.ndarray) -> bytes:
    """Side-by-side log-mel spectrograms (baseline | current) for the dashboard."""
    figure = Figure(figsize=(10, 3.6), dpi=100)
    axes = figure.subplots(1, 2, sharey=True)
    for ax, signal, title in ((axes[0], baseline, "Эталон"), (axes[1], current, "Сейчас")):
        mel = librosa.power_to_db(
            librosa.feature.melspectrogram(
                y=signal.astype(np.float32), sr=SAMPLE_RATE, n_fft=N_FFT, hop_length=FRAME_HOP, n_mels=N_MELS
            ),
            ref=1.0,
        )
        ax.imshow(
            mel,
            origin="lower",
            aspect="auto",
            cmap="magma",
            vmin=-80,
            vmax=20,
            extent=(0, len(signal) / SAMPLE_RATE, 0, N_MELS),
        )
        ax.set_title(title)
        ax.set_xlabel("секунды")
    axes[0].set_ylabel("mel-полоса (низкие → высокие)")
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()
