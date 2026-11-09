"""Deterministic Welch-spectrum descriptors and ru/kk explanation templates."""

from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks, welch

from fibo_ai.schemas.audio import AudioDescriptors

BANDS = [
    ("0_250Hz", 0.0, 250.0),
    ("250_500Hz", 250.0, 500.0),
    ("500_1000Hz", 500.0, 1000.0),
    ("1000_2000Hz", 1000.0, 2000.0),
    ("2000_4000Hz", 2000.0, 4000.0),
    ("4000_8000Hz", 4000.0, 8000.0),
]


def extract_descriptors(
    waveform: NDArray[Any],
    sample_rate: int,
    baseline: dict[str, NDArray[Any]],
) -> AudioDescriptors:
    nperseg = min(4096, max(256, waveform.size))
    frequencies, current_power = welch(waveform, fs=sample_rate, nperseg=nperseg)
    reference_power = np.interp(frequencies, baseline["spectrum_freqs"], baseline["spectrum_mean"])
    band_deltas: dict[str, float] = {}
    for name, low, high in BANDS:
        mask = (frequencies >= low) & (frequencies < high)
        base_energy = max(float(np.mean(reference_power[mask])), 1e-12)
        current_energy = max(float(np.mean(current_power[mask])), 1e-12)
        band_deltas[name] = round(float(10.0 * np.log10(current_energy / base_energy)), 2)

    delta_db = 10.0 * np.log10(np.maximum(current_power, 1e-12) / np.maximum(reference_power, 1e-12))
    peak_indices, properties = find_peaks(delta_db, prominence=4.0, height=6.0, distance=8)
    peaks = [
        {
            "frequency_hz": round(float(frequencies[index]), 1),
            "prominence_db": round(float(prominence), 2),
        }
        for index, prominence in zip(peak_indices, properties.get("prominences", []), strict=False)
        if 100.0 <= frequencies[index] <= 8000.0
    ]
    peaks.sort(key=lambda item: item["prominence_db"], reverse=True)
    peaks = peaks[:5]

    frame_size = max(1, int(0.05 * sample_rate))
    frames = [waveform[i : i + frame_size] for i in range(0, waveform.size, frame_size)]
    frame_rms = np.asarray(
        [np.sqrt(np.mean(np.square(frame, dtype=np.float64))) for frame in frames if frame.size],
        dtype=np.float64,
    )
    impulse = float(np.max(frame_rms) / max(float(np.mean(frame_rms)), 1e-12))
    current_centroid = float(np.sum(frequencies * current_power) / max(np.sum(current_power), 1e-12))
    base_centroid = float(
        np.sum(baseline["spectrum_freqs"] * baseline["spectrum_mean"])
        / max(float(np.sum(baseline["spectrum_mean"])), 1e-12)
    )
    return AudioDescriptors(
        band_deltas_db=band_deltas,
        new_tonal_peaks=peaks,
        impulse_index=round(impulse, 3),
        spectral_centroid_shift_hz=round(current_centroid - base_centroid, 1),
    )


def render_descriptors(descriptors: AudioDescriptors, z_score: float) -> tuple[str, str]:
    loudest = max(descriptors.band_deltas_db.items(), key=lambda pair: pair[1])
    band_label = loudest[0].replace("_", "–")
    db = loudest[1]
    peak = descriptors.new_tonal_peaks[0] if descriptors.new_tonal_peaks else None
    ru = f"Звук отличается от нормы этого станка ({z_score:+.1f}σ). Энергия в полосе {band_label} Гц изменилась на {db:+.1f} дБ."
    kk = f"Дыбыс осы станоктың нормасынан ауытқыды ({z_score:+.1f}σ). {band_label} Гц жолағындағы энергия {db:+.1f} дБ өзгерді."
    if peak:
        hz = float(peak["frequency_hz"])
        ru += f" Новый тональный пик: {hz:.0f} Гц."
        kk += f" Жаңа тоналды шың: {hz:.0f} Гц."
    return ru, kk
