"""Create a compact side-by-side baseline/current spectrogram PNG."""

import base64
import io
from typing import Any

import matplotlib
import numpy as np
from numpy.typing import NDArray
from scipy.signal import spectrogram

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render_spectrogram_pair(current_waveform: NDArray[Any], sample_rate: int, baseline: dict[str, NDArray[Any]]) -> str:
    frequencies, times, power = spectrogram(current_waveform, fs=sample_rate, nperseg=512, noverlap=384, nfft=512)
    current_db = 10.0 * np.log10(np.maximum(power, 1e-12))
    base_db = baseline["spectrogram_mean"]
    if base_db.shape[0] != current_db.shape[0]:
        raise ValueError("BASELINE_VERSION_MISMATCH")
    vmin = float(min(np.percentile(base_db, 5), np.percentile(current_db, 5)))
    vmax = float(max(np.percentile(base_db, 99), np.percentile(current_db, 99)))
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True, constrained_layout=True)
    axes[0].imshow(
        base_db,
        origin="lower",
        aspect="auto",
        extent=[0, 2, 0, sample_rate / 2],
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    axes[0].set_title("Baseline (normal)")
    axes[1].imshow(
        current_db,
        origin="lower",
        aspect="auto",
        extent=[float(times[0]), float(times[-1]), 0, sample_rate / 2],
        cmap="magma",
        vmin=vmin,
        vmax=vmax,
    )
    axes[1].set_title("Current recording")
    for ax in axes:
        ax.set_xlabel("Time (s)")
        ax.set_ylim(0, min(8000, sample_rate / 2))
    axes[0].set_ylabel("Frequency (Hz)")
    fig.colorbar(axes[1].images[0], ax=axes, label="Power (dB)", shrink=0.85)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
