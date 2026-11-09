"""Audio embedding implementations with native-rate handling."""

import os
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.request import urlretrieve

import numpy as np
from numpy.typing import NDArray
from scipy.fft import dct
from scipy.signal import stft


class AudioEmbedder(Protocol):
    embedder_id: str
    version: str
    sample_rate: int

    def embed(self, waveform: NDArray[Any]) -> NDArray[Any]: ...


def l2_normalize(vector: NDArray[Any]) -> NDArray[Any]:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-12 else vector


def make_windows(waveform: NDArray[Any], sample_rate: int, duration_s: float, overlap: float) -> list[NDArray[Any]]:
    window_size = max(1, int(round(sample_rate * duration_s)))
    step = max(1, int(round(window_size * (1.0 - overlap))))
    if waveform.size <= window_size:
        return [np.pad(waveform, (0, max(0, window_size - waveform.size)))[:window_size]]
    starts = list(range(0, waveform.size - window_size + 1, step))
    final_start = waveform.size - window_size
    if starts[-1] != final_start:
        starts.append(final_start)
    return [waveform[start : start + window_size] for start in starts]


def _hz_to_mel(hz: NDArray[Any]) -> NDArray[Any]:
    return cast(NDArray[Any], 2595.0 * np.log10(1.0 + hz / 700.0))


def _mel_to_hz(mel: NDArray[Any]) -> NDArray[Any]:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


class MfccBaselineEmbedder:
    embedder_id = "mfcc_baseline"
    version = "mfcc-1"
    sample_rate = 16000

    def embed(self, waveform: NDArray[Any]) -> NDArray[Any]:
        _, _, spectrum = stft(
            waveform,
            fs=self.sample_rate,
            nperseg=400,
            noverlap=240,
            nfft=512,
            boundary=None,
        )
        power = np.abs(spectrum) ** 2
        edges = _mel_to_hz(np.linspace(_hz_to_mel(np.array([20.0]))[0], _hz_to_mel(np.array([7600.0]))[0], 42))
        bins = np.floor(edges * 512 / self.sample_rate).astype(int)
        bank = np.zeros((40, power.shape[0]), dtype=np.float64)
        for i in range(40):
            left, center, right = bins[i : i + 3]
            center = max(center, left + 1)
            right = max(right, center + 1)
            for index in range(max(0, left), min(center, len(bank[i]))):
                bank[i, index] = (index - left) / (center - left)
            for index in range(max(0, center), min(right, len(bank[i]))):
                bank[i, index] = (right - index) / (right - center)
        mel_energy = np.maximum(bank @ power, 1e-10)
        coeff = dct(np.log(mel_energy), type=2, axis=0, norm="ortho")[:13]
        result = np.concatenate([coeff.mean(axis=1), coeff.std(axis=1)])
        return l2_normalize(result)


class PannsCnn14Embedder:
    embedder_id = "panns_cnn14"
    version = "cnn14-audioset"
    sample_rate = 32000

    def __init__(self) -> None:
        model_dir = Path(os.environ.get("FIBO_DATA_DIR", "artifacts")) / "models" / "audio"
        package_dir = model_dir / "panns_data"
        package_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = package_dir / "Cnn14_mAP=0.431.pth"
        if not checkpoint.exists() or checkpoint.stat().st_size < 300_000_000:
            urlretrieve(
                "https://zenodo.org/records/3987831/files/Cnn14_mAP%3D0.431.pth?download=1",
                checkpoint,
            )
        labels = package_dir / "class_labels_indices.csv"
        if not labels.exists():
            urlretrieve(
                "https://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv",
                labels,
            )
        try:
            from unittest.mock import patch

            with patch.object(Path, "home", return_value=model_dir):
                from panns_inference import AudioTagging
        except ImportError as exc:
            raise RuntimeError("PANNs requires the optional panns-inference and torch packages") from exc
        self._tagger: Any = AudioTagging(checkpoint_path=str(checkpoint), device="cpu")

    def embed(self, waveform: NDArray[Any]) -> NDArray[Any]:
        _, embedding = self._tagger.inference(waveform.astype(np.float32)[None, :])
        return l2_normalize(np.asarray(embedding)[0])


class AstEmbedder:
    embedder_id = "ast"
    version = "MIT/ast-finetuned-audioset-10-10-0.4593"
    sample_rate = 16000

    def __init__(self) -> None:
        model_cache = Path(os.environ.get("FIBO_DATA_DIR", "artifacts")) / "models" / "hf_cache"
        model_cache.mkdir(parents=True, exist_ok=True)
        hf_home = model_cache.parent / "hf_home"
        hf_home.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_home.resolve()))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        try:
            from transformers import AutoFeatureExtractor, AutoModel
        except ImportError as exc:
            raise RuntimeError("AST requires the optional transformers and torch packages") from exc
        self._extractor: Any = AutoFeatureExtractor.from_pretrained(self.version, cache_dir=model_cache)  # type: ignore[no-untyped-call]
        self._model = AutoModel.from_pretrained(self.version, cache_dir=model_cache).eval().to("cpu")

    def embed(self, waveform: NDArray[Any]) -> NDArray[Any]:
        import torch

        batch = self._extractor(waveform.astype(np.float32), sampling_rate=self.sample_rate, return_tensors="pt")
        with torch.inference_mode():
            output = self._model(**batch)
        return l2_normalize(output.last_hidden_state.mean(dim=1).cpu().numpy()[0])


def get_embedder(embedder_id: str) -> AudioEmbedder:
    if embedder_id == "mfcc_baseline":
        return MfccBaselineEmbedder()
    if embedder_id == "panns_cnn14":
        return PannsCnn14Embedder()
    if embedder_id == "ast":
        return AstEmbedder()
    raise ValueError(f"Unknown audio embedder: {embedder_id}")
